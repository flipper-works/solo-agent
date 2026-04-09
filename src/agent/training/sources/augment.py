"""LLM自動生成によるSFTデータ増強。

既存の curated 例をシードとして、LLM に類似パターンを生成させる。
同じタグ (identity / honesty / unknown) で変化球を増やす。
"""
from __future__ import annotations

import json

from agent.llm.base import BaseLLM, Message
from agent.training.schema import SFTMessage, SFTRecord

_AUGMENT_SYSTEM = (
    "あなたは SFT 学習データの増強ツールです。\n"
    "与えられたサンプル (system / user / assistant の組) と同じ意図・品質を持つ、\n"
    "しかし文面が異なる新しい会話例を生成してください。\n\n"
    "## ルール\n"
    '1. 出力は必ず {"examples": [{"user": "...", "assistant": "..."}, ...]} の形式で返すこと。\n'
    "2. user の質問は自然な言い回しのバリエーションにする。\n"
    "3. assistant の回答は元サンプルと同程度の詳しさ・トーンを保つ。\n"
    "4. 事実を捏造しない。元サンプルの正しさを維持すること。\n"
    "5. 日本語で出力。\n"
)


async def augment_from_seed(
    llm: BaseLLM,
    seed: SFTRecord,
    n_variants: int = 3,
) -> list[SFTRecord]:
    """1つの seed record から n_variants 個の新しい record を生成。"""
    system_msg = ""
    user_msg = ""
    asst_msg = ""
    for m in seed.messages:
        if m.role == "system":
            system_msg = m.content
        elif m.role == "user":
            user_msg = m.content
        elif m.role == "assistant":
            asst_msg = m.content

    prompt = (
        f"# 元サンプル\n"
        f"system: {system_msg}\n"
        f"user: {user_msg}\n"
        f"assistant: {asst_msg}\n\n"
        f"上記と同じ意図を持つ、別の言い回しの会話例を {n_variants} 個生成してください。"
    )
    raw = await llm.generate(
        [
            Message(role="system", content=_AUGMENT_SYSTEM),
            Message(role="user", content=prompt),
        ],
        options={"temperature": 0.7},
        format="json",
    )

    # parse JSON — LLM may return:
    # 1) [{"user":..,"assistant":..}, ...]     (ideal)
    # 2) {"examples": [{..}, ..]}              (wrapped array)
    # 3) {"user":..,"assistant":..}             (single item)
    # 4) {"variation":1,"conversation":".."}    (Gemma quirk)
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        return []

    items: list[dict] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # try to find a nested array
        for key in ("examples", "data", "variants", "results", "conversations"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items:
            # single item dict with user/assistant
            if "user" in data and "assistant" in data:
                items = [data]
            elif "conversation" in data:
                # Gemma quirk: {"conversation": "user: ...\nassistant: ..."}
                items = [data]

    records: list[SFTRecord] = []
    for item in items:
        u = item.get("user", "")
        a = item.get("assistant", "")
        # Handle Gemma's "conversation" format
        if not u and "conversation" in item:
            conv = item["conversation"]
            if "user:" in conv and "assistant:" in conv:
                parts = conv.split("assistant:", 1)
                u = parts[0].replace("user:", "").strip()
                a = parts[1].strip() if len(parts) > 1 else ""
        if not u or not a:
            continue
        msgs: list[SFTMessage] = []
        if system_msg:
            msgs.append(SFTMessage(role="system", content=system_msg))
        msgs.append(SFTMessage(role="user", content=u))
        msgs.append(SFTMessage(role="assistant", content=a))
        records.append(
            SFTRecord(messages=msgs, source="augment", tag=seed.tag)
        )
    return records


async def augment_all(
    llm: BaseLLM,
    seeds: list[SFTRecord],
    n_variants: int = 3,
) -> list[SFTRecord]:
    """全 seed から増強データを生成。"""
    all_augmented: list[SFTRecord] = []
    for seed in seeds:
        variants = await augment_from_seed(llm, seed, n_variants)
        all_augmented.extend(variants)
    return all_augmented
