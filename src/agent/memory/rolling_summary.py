"""L2 Warm: 古い会話を LLM で階層的に圧縮要約して保持。

L1 (ShortTermMemory) があふれた古いターンを受け取り、要約済みの単一テキストに
畳み込む。Plannerプロンプト構築時に L1直近 + L2要約 として使う。

階層化:
- 既存要約 + 新しい古いターン群 → 新しい要約 (累積圧縮)
"""
from __future__ import annotations

from agent.llm.base import BaseLLM, Message
from agent.memory.short_term import Turn

_SYSTEM = (
    "あなたは会話履歴の要約器です。"
    "与えられた既存要約と新しい会話ターンを統合し、"
    "後続のエージェントが文脈を失わないために必要な事実・決定・未解決課題を"
    "日本語の箇条書き5〜10項目で要約してください。"
    "余談・装飾は省く。新規情報を優先して残す。"
)


class RollingSummary:
    def __init__(self, llm: BaseLLM, max_chars: int = 2000) -> None:
        self.llm = llm
        self.max_chars = max_chars
        self._summary: str = ""

    @property
    def text(self) -> str:
        return self._summary

    def __bool__(self) -> bool:
        return bool(self._summary)

    async def fold_in(self, evicted: list[Turn]) -> None:
        """L1から押し出された古いターン群を要約に畳み込む。"""
        if not evicted:
            return
        evicted_text = "\n".join(f"[{t.role}] {t.content}" for t in evicted)
        prompt = (
            f"# 既存要約\n{self._summary or '(まだ要約なし)'}\n\n"
            f"# 新しく追加するターン\n{evicted_text}\n\n"
            "上記を統合した新しい要約を出力してください。"
        )
        result = await self.llm.generate(
            [
                Message(role="system", content=_SYSTEM),
                Message(role="user", content=prompt),
            ],
            options={"temperature": 0.2},
        )
        # truncate hard cap
        self._summary = result.strip()[: self.max_chars]

    def reset(self) -> None:
        self._summary = ""
