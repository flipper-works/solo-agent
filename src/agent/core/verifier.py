"""Verifier: タスクと実行トレースを照合し、真の達成を検証する独立コンポーネント。

Observer から「結果の妥当性検証」責務を切り出した。
- LLM-as-judge: 現状実装。LLM に5項目チェックリストを答えさせる
- 将来: ルールベース or FT専用検証モデルに差し替え可能
"""
from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, Field

from agent.core.executor import ExecutionTrace
from agent.llm.base import BaseLLM, Message


class VerifyResult(BaseModel):
    passed: bool = Field(description="タスクの本質的な目標が達成されていれば True")
    issues: list[str] = Field(default_factory=list, description="未達成・疑わしい点")
    summary: str = Field(default="", description="検証の総括 (1文)")


class BaseVerifier(Protocol):
    async def verify(self, task: str, trace: ExecutionTrace) -> VerifyResult: ...


_VERIFY_SYSTEM = (
    "あなたはタスク実行結果の検証者です。実行ログを見て、ユーザーの本来の目標が"
    "本当に達成されているかを厳しく判定してください。\n\n"
    "## チェックリスト (全て確認)\n"
    "V1. ユーザーの指示の字面が満たされているか? (順序指定・ツール制約・失敗経由要求等)\n"
    "V2. 実行結果の中身は妥当か? (数値計算なら桁数・先頭文字、ファイル操作なら期待ファイル名・内容)\n"
    "V3. Plannerが指示を「親切に先回り」して飛ばしていないか?\n"
    "V4. 結果として作られたファイル/出力は、ユーザーの期待する形式・内容と一致しているか?\n"
    "V5. ステップの ok=True は『プロセスが落ちなかった』だけを意味する。中身の正しさは別途判断すること。\n"
    "V6. コードレビュー系タスクで、元コードに本当にバグがあったのか? 無理に問題を捏造していないか? バグがないなら「問題なし」が正しい回答。\n\n"
    "## 出力 (JSONのみ)\n"
    '{"passed": true|false, "issues": ["<日本語の問題点>", ...], "summary": "<日本語1文>"}'
)


class LLMVerifier:
    """LLM-as-judge 検証実装。"""

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def _trace_to_text(self, trace: ExecutionTrace) -> str:
        lines = []
        for i, rec in enumerate(trace.records, 1):
            lines.append(
                f"[step {i}] tool={rec.step.tool} args={rec.step.args} "
                f"ok={rec.result.ok}\n  out={rec.result.output[:500]}\n  err={rec.result.error[:300]}"
            )
        return "\n".join(lines)

    async def verify(self, task: str, trace: ExecutionTrace) -> VerifyResult:
        user = f"# タスク\n{task}\n\n# 実行ログ\n{self._trace_to_text(trace)}"
        raw = await self.llm.generate(
            [
                Message(role="system", content=_VERIFY_SYSTEM),
                Message(role="user", content=user),
            ],
            options={"temperature": 0.1},
            format="json",
        )
        # extract JSON object
        start = raw.find("{")
        end = raw.rfind("}")
        body = raw[start : end + 1] if start != -1 and end != -1 else raw
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return VerifyResult(
                passed=False,
                issues=[f"verifier parse error: {raw[:200]}"],
                summary="verifier output unparseable",
            )
        return VerifyResult.model_validate(data)
