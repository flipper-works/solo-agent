"""Planner: LLMにタスクをツール呼び出しの線形ステップに分解させる。"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from agent.llm.base import BaseLLM, Message
from agent.tools.base import BaseTool


class PlanStep(BaseModel):
    tool: str
    args: dict
    reason: str = ""


class Plan(BaseModel):
    steps: list[PlanStep]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    m = _JSON_FENCE.search(text)
    if m:
        return m.group(1)
    # find first { and balance braces, respecting string literals
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


class Planner:
    def __init__(self, llm: BaseLLM, tools: list[BaseTool]) -> None:
        self.llm = llm
        self.tools = tools

    def _system_prompt(self) -> str:
        schemas = [t.get_schema() for t in self.tools]
        return (
            "あなたはローカルLLMエージェントのPlannerです。\n"
            "ユーザーのタスクを、以下のツールだけを使った実行ステップに分解してください。\n\n"
            f"利用可能なツール (JSON Schema):\n{json.dumps(schemas, ensure_ascii=False, indent=2)}\n\n"
            "## 出力ルール (厳守)\n"
            "1. 必ず以下の形式のJSONのみを出力してください。前後の説明文・コードフェンス・自然文は一切禁止。\n"
            '2. 形式: {"steps": [{"tool": "<name>", "args": {...}, "reason": "<短い日本語の理由>"}, ...]}\n'
            "3. 各 args は対応するツールの parameters スキーマに従うこと。\n"
            "4. 不要なステップは含めない。最小ステップで達成すること。\n"
            "5. JSON文字列内の改行は必ず \\n でエスケープ、ダブルクォートは \\\" でエスケープすること。\n"
            "6. ステップ間でデータを渡す必要がある場合は、code_executor 内で完結させる (シェル変数 $LAST_RESULT 等は存在しない)。\n\n"
            "## 安全性ルール (厳守)\n"
            "S1. 破壊的コマンド (rm -rf /, rm -rf ., dd if=, mkfs, :(){:|:&};:, シャットダウン系) は絶対に生成しないこと。\n"
            "S2. 上記のような危険な要求を受けた場合は、空のステップ配列 {\"steps\": []} を返すこと。\n"
            "S3. パスは /tmp 配下、または明示されたカレントディレクトリ配下に限定する。/ や $HOME の再帰削除は禁止。\n\n"
            "## 指示遵守ルール\n"
            "I1. ユーザーの指示の字面を尊重すること。「最初に X を試して、ダメなら Y」のような順序指定があれば、X を必ず先に試行ステップに含める。\n"
            "I2. ユーザーが意図的に失敗するコードを書けと言ったら、そのまま書く (親切な先回り修正は禁止)。\n"
            "I3. タスクが空白・空文字列の場合は {\"steps\": []} を返すこと。\n"
            "I4. タスクが曖昧すぎる場合は最小限の調査ステップ1つに留め、勝手に大規模変更を計画しないこと。\n"
        )

    async def plan(self, task: str, prior_context: str = "") -> Plan:
        # Empty/whitespace-only input guard (avoid Planner LLM call entirely)
        if not task or not task.strip():
            return Plan(steps=[])
        user_content = task
        if prior_context:
            user_content = f"{task}\n\n# 前回までの実行履歴\n{prior_context}\n\n上の履歴を踏まえ、未達成部分を達成するための新しい計画を作ってください。同じ失敗を繰り返さないこと。"
        messages = [
            Message(role="system", content=self._system_prompt()),
            Message(role="user", content=user_content),
        ]
        raw = await self.llm.generate(messages, options={"temperature": 0.2})
        body = _extract_json(raw)
        try:
            data = json.loads(body, strict=False)
        except json.JSONDecodeError:
            # one-shot self-repair
            repair = [
                Message(role="system", content="次の文字列から `steps` キーを持つ正しいJSONだけを抽出して出力してください。説明は禁止。"),
                Message(role="user", content=raw),
            ]
            body = _extract_json(await self.llm.generate(repair))
            data = json.loads(body, strict=False)
        return Plan.model_validate(data)
