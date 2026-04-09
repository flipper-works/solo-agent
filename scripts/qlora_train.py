"""QLoRA fine-tuning script for Gemma 3 12B using unsloth.

Usage (FT 専用 venv):
    scripts/ft_env/.venv/bin/python scripts/qlora_train.py
    scripts/ft_env/.venv/bin/python scripts/qlora_train.py --epochs 3 --lr 2e-4

Setup (初回のみ):
    python3.12 -m venv scripts/ft_env/.venv
    scripts/ft_env/.venv/bin/pip install "unsloth[cu124-torch260]"

Environment:
    RTX 4070 Ti SUPER (16GB VRAM)
    Isolated venv to avoid dependency conflicts with main project
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="QLoRA fine-tuning for Gemma 3")
    p.add_argument("--data", type=str, default="data/sft/train.jsonl")
    p.add_argument("--val", type=str, default="data/sft/val.jsonl")
    p.add_argument("--out", type=str, default="models/lora_gemma3_12b")
    p.add_argument("--base-model", type=str, default="unsloth/gemma-3-12b-it-bnb-4bit")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--max-seq-len", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=16)
    p.add_argument("--lora-dropout", type=float, default=0.0)
    p.add_argument("--save-gguf", action="store_true", default=True)
    return p.parse_args()


def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def format_for_training(record: dict) -> str:
    """Convert ChatML messages to Gemma chat template string."""
    parts = []
    for msg in record.get("messages", []):
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            parts.append(f"<start_of_turn>user\n[System: {content}]<end_of_turn>")
        elif role == "user":
            parts.append(f"<start_of_turn>user\n{content}<end_of_turn>")
        elif role == "assistant":
            parts.append(f"<start_of_turn>model\n{content}<end_of_turn>")
    return "\n".join(parts)


def main():
    args = parse_args()
    print(f"[qlora] Loading data from {args.data}")

    train_data = load_jsonl(args.data)
    print(f"[qlora] Training samples: {len(train_data)}")

    # --- Model loading ---
    print(f"[qlora] Loading base model: {args.base_model}")
    from unsloth import FastModel

    model, tokenizer = FastModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=True,
    )

    # --- LoRA setup ---
    print(f"[qlora] Applying LoRA: r={args.lora_r}, alpha={args.lora_alpha}")
    model = FastModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    # --- Dataset preparation ---
    print("[qlora] Formatting dataset...")
    from datasets import Dataset

    formatted = [{"text": format_for_training(r)} for r in train_data]
    dataset = Dataset.from_list(formatted)

    # --- Training ---
    print(f"[qlora] Training: epochs={args.epochs}, lr={args.lr}, "
          f"batch={args.batch_size}, grad_accum={args.grad_accum}")
    from trl import SFTTrainer, SFTConfig

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir=args.out,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            warmup_steps=5,
            logging_steps=1,
            save_strategy="epoch",
            fp16=False,
            bf16=True,
            optim="adamw_8bit",
            seed=42,
            max_seq_length=args.max_seq_len,
            dataset_text_field="text",
            packing=False,
        ),
    )

    print("[qlora] Starting training...")
    stats = trainer.train()
    print(f"[qlora] Training complete. Loss: {stats.training_loss:.4f}")

    # --- Save LoRA adapter ---
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out / "lora_adapter")
    tokenizer.save_pretrained(out / "lora_adapter")
    print(f"[qlora] LoRA adapter saved to {out / 'lora_adapter'}")

    # --- Export to GGUF (for Ollama) ---
    # Must be done while model is still in memory (not reloaded)
    if args.save_gguf:
        print("[qlora] Exporting to GGUF (Q4_K_M)...")
        print("[qlora] This downloads full-precision weights (~24GB) and merges LoRA.")
        print("[qlora] Requires stable internet + ~30GB disk space.")
        gguf_dir = out / "gguf"
        gguf_dir.mkdir(parents=True, exist_ok=True)
        try:
            model.save_pretrained_gguf(
                str(gguf_dir),
                tokenizer,
                quantization_method="q4_k_m",
            )
            print(f"[qlora] GGUF saved to {gguf_dir}")
            # Find the actual gguf file
            gguf_files = list(gguf_dir.glob("*.gguf"))
            if gguf_files:
                gguf_path = gguf_files[0]
                # Create Ollama Modelfile
                modelfile = gguf_dir / "Modelfile"
                modelfile.write_text(f"FROM ./{gguf_path.name}\n")
                print(f"\n[qlora] To import into Ollama:")
                print(f"  cd {gguf_dir}")
                print(f"  ollama create gemma3-ft -f Modelfile")
                print(f"  ollama run gemma3-ft")
        except Exception as e:
            print(f"[qlora] GGUF export failed: {e}")
            print("[qlora] LoRA adapter is still saved. You can retry GGUF later with:")
            print(f"  scripts/ft_env/.venv/bin/python scripts/qlora_train.py --skip-train --save-gguf")

    print("\n[qlora] Done!")


if __name__ == "__main__":
    main()
