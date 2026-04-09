# FT / DPO 実施レポート — 2026-04-09〜10

## 概要

Gemma 3 12B に対して QLoRA SFT と DPO を試みた記録。
k3 (自己同一性) と k4 (ハルシネーション) は System Prompt で解決。
c3 (Yes-bias) は FT/DPO 環境の互換性問題で未解決、実用回避策で対応。

---

## 1. QLoRA SFT

### 環境
- unsloth[cu124-torch260] + RTX 4070 Ti SUPER (16GB)
- 独立 venv (`scripts/ft_env/.venv`)

### データ
- 手動キュレーション 14件 (identity 5, honesty 4, unknown 5)
- LLM自動増強 55件 (Gemma 3 自身で生成)
- エピソード記憶 3件
- 合計: **69件** (train 63 / val 6)

### 結果
- 学習: 成功 (341秒、loss 1.83→0.64)
- GGUF変換: unsloth 内部バグで失敗。llama.cpp で Q8_0 (12GB) に変換成功
- Ollama 取り込み: 成功 (`gemma3-ft`)
- **効果: ほぼゼロ** — k3/k4/c3 全て未改善

### 原因分析
1. **データ量不足**: 69件で 12B パラメータモデルの振る舞いは変えられない
2. **増強の質**: Gemma 3 自身で増強 → 自分のバイアスを再生産 (「Gemini」バイアスを増幅)
3. **Q8_0 量子化**: LoRA の微小重み変化が量子化ノイズで打ち消された可能性

---

## 2. System Prompt (Ollama Modelfile)

### 方法
```
FROM gemma3:12b
SYSTEM """あなたは Google が公開しているオープンウェイトモデル Gemma 3 (12Bパラメータ版) です。
Gemini とは別のモデルファミリーです。Ollama 経由でローカル実行されています。
自分のアイデンティティについて聞かれたら、正確に答えてください。
知らないことは知らないと素直に答えてください。"""
```

### 結果
- **k3 自己同一性: ✅ 完全解決** — 「Gemma 3 (12B) です」と正確に回答
- **k4 ハルシネーション: ✅ 解決** — 架空イベントに「知りません」と回答
- **c3 Yes-bias: ❌ 未解決** — 「バグを指摘して」のユーザー指示が System Prompt を上回る

### 教訓
69件の SFT より System Prompt 1行の方が効果が高かった。
FT は「モデルの根本的な傾向を変える」ためのもので、「指示に従わせる」には過剰。

---

## 3. DPO 試行

### 目的
c3 (Yes-bias) を DPO で矯正する。
SFT は「正解を見せて真似させる」、DPO は「正解と不正解のペアで選好を学ばせる」。
「バグがないのにバグを発見する (rejected)」vs「バグなしと素直に言う (chosen)」のペアで学習。

### データ
- `evals/sft_curated/dpo_honesty.yaml`: 15 chosen/rejected ペア
- バグなし Python コード × 15種 (is_even, add, reverse_string, clamp 等)
- 1件のみ逆パターン (本当にセキュリティ問題がある SHA-256 コード) をバランス用に含む

### 試行1: unsloth + trl DPO
- triton `AttrsDescriptor` import エラーで失敗
- torch CPU/CUDA 入れ替え、依存地獄で断念

### 試行2: transformers + peft + trl (unsloth なし)
- 環境: transformers 5.5.2, peft 0.18.1, trl 1.0.0
- モデルロード: 成功 (4bit 量子化、LoRA 68M trainable params)
- **学習: 失敗** — `ValueError: token_type_ids is required as a model input when training`
- 原因: Gemma 3 の `modeling_gemma3.py` 内 `create_causal_mask_mapping` が
  `token_type_ids` を必須入力として要求。trl の DPOTrainer はこれを渡さない。
  tokenizer 側で `model_input_names` から除外しても、model forward が直接チェックするため回避不能。
- **Gemma 3 固有の問題**: Llama 系モデルでは発生しない

### 結論
Gemma 3 + DPO は transformers 5.x / trl 1.x の時点で非互換。
以下のいずれかが揃えば再挑戦可能:
1. trl が Gemma 3 の token_type_ids 対応を入れる (upstream fix 待ち)
2. transformers が Gemma 3 の token_type_ids 要求を緩和する
3. Gemma 3 以外のベースモデル (Llama 3.1 等) に切り替える

---

## 4. 最終対応方針

| 課題 | 対応 | 状態 |
|---|---|---|
| k3 自己同一性 | Ollama Modelfile SYSTEM prompt | ✅ 解決済 |
| k4 ハルシネーション | 同上 | ✅ 解決済 |
| c3 Yes-bias | Planner/Chat System Prompt 強化 + Verifier 検知で実用回避 | ⚠️ 暫定対応 |
| c3 根本解決 | DPO (Gemma 3 互換性が安定した時点で再挑戦) | 📋 保留 |

### 保存済み資産 (再挑戦時に使える)
- `evals/sft_curated/dpo_honesty.yaml` — DPO データ 15ペア
- `evals/sft_curated/identity.yaml` — 自己同一性 SFT データ 5例
- `evals/sft_curated/honesty.yaml` — Yes-bias SFT データ 4例
- `evals/sft_curated/unknown.yaml` — ハルシネ抑制 SFT データ 5例
- `scripts/dpo_train.py` — DPO 学習スクリプト (HF stack版)
- `scripts/qlora_train.py` — SFT 学習スクリプト (unsloth版)
- `src/agent/training/` — SFT データパイプライン (curated / episodes / augment / builder / exporter)
