"""Chat Agent: 会話中にツールを自律的に使えるチャットモード。

Claude Code のように「ファイル見て」「コマンド実行して」と言われたら
ツールを呼び、結果を見て回答する。素の LLM チャットとエージェント実行の統合。

フロー:
  user: "デスクトップのファイルを見せて"
    ↓
  LLM: ツール呼び出しが必要か判断
    ↓ YES
  Planner: ツール呼び出し計画
  Executor: 実行
  LLM: 結果を見て自然言語で回答
    ↓ NO
  LLM: 通常のテキスト応答
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from agent.core.executor import Executor
from agent.core.planner import Planner
from agent.llm.base import BaseLLM, Message
from agent.tools.base import BaseTool


_CHAT_SYSTEM = (
    "あなたはローカルで動作するAIアシスタントです。\n"
    "ユーザーの要求に対して、必要であれば以下のツールを使って情報を取得・操作できます。\n\n"
    "ツールを使うべき場合:\n"
    "- ファイルの読み書き・検索\n"
    "- シェルコマンドの実行\n"
    "- Python コードの実行\n"
    "- ディレクトリの中身の確認\n"
    "- その他、実際のシステム操作が必要な場合\n\n"
    "ツールを使わない場合:\n"
    "- 一般的な質問への回答\n"
    "- コードの説明・レビュー\n"
    "- 概念的な議論\n\n"
    "ツールが必要と判断したら、以下のJSON形式で応答してください:\n"
    '{"action": "use_tools", "task": "<ツールで実行したいタスクの要約>"}\n\n'
    "ツールが不要なら、通常の自然文で応答してください。\n"
    "知らないことは知らないと素直に答えてください。\n"
    "コードレビューで問題がなければ「問題ありません」と正直に答えてください。\n"
)


class ChatAgent:
    """ツール統合チャット。会話しながら必要に応じてツールを呼ぶ。"""

    def __init__(
        self,
        llm: BaseLLM,
        tools: list[BaseTool],
        system: str = "",
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.planner = Planner(llm, tools)
        self.executor = Executor(tools)
        self.history: list[Message] = [
            Message(role="system", content=system or _CHAT_SYSTEM)
        ]

    async def send(self, user_input: str) -> str:
        """ユーザー入力を処理し、応答を返す。ツール実行が必要なら自動で呼ぶ。"""
        self.history.append(Message(role="user", content=user_input))

        # LLM に判断させる: ツールが必要か？
        response = await self.llm.generate(
            self.history, options={"temperature": 0.3}
        )

        # ツール呼び出し判定
        tool_task = self._extract_tool_task(response)

        if tool_task:
            # ツール実行フロー
            result_text = await self._execute_task(tool_task)
            # ツール結果を踏まえて最終回答を生成
            self.history.append(
                Message(role="assistant", content=f"[ツール実行中: {tool_task}]")
            )
            self.history.append(
                Message(role="user", content=f"ツール実行結果:\n{result_text}\n\nこの結果をユーザーにわかりやすく説明してください。")
            )
            final = await self.llm.generate(
                self.history, options={"temperature": 0.3}
            )
            self.history.append(Message(role="assistant", content=final))
            return final
        else:
            # 通常応答
            self.history.append(Message(role="assistant", content=response))
            return response

    async def send_stream(self, user_input: str) -> AsyncIterator[str]:
        """ストリーミング版。ツール実行時は途中経過も返す。"""
        self.history.append(Message(role="user", content=user_input))

        response = await self.llm.generate(
            self.history, options={"temperature": 0.3}
        )

        tool_task = self._extract_tool_task(response)

        if tool_task:
            yield f"[ツール実行中: {tool_task}]\n"
            result_text = await self._execute_task(tool_task)
            yield f"[実行完了]\n\n"

            self.history.append(
                Message(role="assistant", content=f"[ツール実行中: {tool_task}]")
            )
            self.history.append(
                Message(role="user", content=f"ツール実行結果:\n{result_text}\n\nこの結果をユーザーにわかりやすく説明してください。")
            )
            async for token in self.llm.stream(
                self.history, options={"temperature": 0.3}
            ):
                yield token
            # rebuild full response from stream for history
            # (simplified: re-generate non-streaming for history)
            final = await self.llm.generate(
                self.history, options={"temperature": 0.3}
            )
            self.history.append(Message(role="assistant", content=final))
        else:
            self.history.append(Message(role="assistant", content=response))
            for char_chunk in self._chunk_text(response):
                yield char_chunk

    def _extract_tool_task(self, response: str) -> str | None:
        """LLM 応答からツール呼び出し意図を抽出。"""
        try:
            # JSON 形式で返ってきた場合
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(response[start : end + 1])
                if data.get("action") == "use_tools" and data.get("task"):
                    return data["task"]
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    async def _execute_task(self, task: str) -> str:
        """Planner→Executor でタスクを実行し、結果テキストを返す。"""
        try:
            plan = await self.planner.plan(task)
            if not plan.steps:
                return "(実行するステップがありません)"
            trace = await self.executor.run(plan)
            lines = []
            for i, rec in enumerate(trace.records, 1):
                mark = "OK" if rec.result.ok else "ERR"
                lines.append(f"[{i}] {mark} {rec.step.tool}")
                if rec.result.output:
                    lines.append(f"  → {rec.result.output[:1000]}")
                if rec.result.error:
                    lines.append(f"  ! {rec.result.error[:500]}")
            return "\n".join(lines)
        except Exception as e:
            return f"エラー: {type(e).__name__}: {e}"

    def _chunk_text(self, text: str, size: int = 4) -> list[str]:
        """テキストを小さなチャンクに分割 (ストリーミング風)。"""
        return [text[i : i + size] for i in range(0, len(text), size)]
