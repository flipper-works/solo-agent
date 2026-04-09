"""Observer: 実行結果を評価し、完了/再計画/失敗を判断。"""
from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from agent.core.executor import ExecutionTrace
from agent.llm.base import BaseLLM, Message


class Verdict(str, Enum):
    DONE = "done"
    REPLAN = "replan"
    FAIL = "fail"


class Observation(BaseModel):
    verdict: Verdict
    summary: str = ""
    next_hint: str = ""


class Observer:
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

    async def observe(self, task: str, trace: ExecutionTrace) -> Observation:
        sys = (
            "あなたはローカルLLMエージェントのObserverです。タスクの『真の達成』を厳しく検証する役割を担います。\n"
            "与えられたタスクと実行ログを見て、次のいずれかを判定してください:\n"
            "  done   : タスクの本質的な目標が達成された (単にステップが ok だっただけでは不十分)\n"
            "  replan : 修正可能。再計画すべき\n"
            "  fail   : 復帰不能\n\n"
            "## 検証チェックリスト (done判定の前に必ず確認)\n"
            "V1. ユーザーの指示の字面が満たされているか? (順序指定・ツール制約・失敗経由の要求等)\n"
            "V2. 実行結果の中身は妥当か? (数値計算なら桁数・先頭文字、ファイル操作なら期待ファイル名・内容)\n"
            "V3. Plannerが指示を「親切に先回り」して飛ばしていないか? (例: NameError出せという指示で出さなかった等)\n"
            "V4. 結果として作られたファイル/出力は、ユーザーの期待する形式・内容と一致しているか?\n"
            "V5. ステップの ok=True は『プロセスが落ちなかった』だけを意味する。中身の正しさは別途判断すること。\n\n"
            "上記いずれか1つでも疑わしい点があれば、done ではなく replan を選び、next_hint で具体的に指摘すること。\n\n"
            "出力は次のJSONのみ (説明文・コードフェンス禁止):\n"
            '{"verdict": "done|replan|fail", "summary": "<日本語1文>", "next_hint": "<replan時の方針>"}'
        )
        user = f"# タスク\n{task}\n\n# 実行ログ\n{self._trace_to_text(trace)}"
        raw = await self.llm.generate(
            [Message(role="system", content=sys), Message(role="user", content=user)],
            options={"temperature": 0.1},
        )
        # extract JSON
        start = raw.find("{")
        end = raw.rfind("}")
        body = raw[start : end + 1] if start != -1 and end != -1 else raw
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Observation(verdict=Verdict.FAIL, summary=f"observer parse error: {raw[:200]}")
        return Observation.model_validate(data)
