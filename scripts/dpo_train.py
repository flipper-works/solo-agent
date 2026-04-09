"""DPO fine-tuning for Gemma 3 12B — unsloth-free version.

Uses: transformers + peft + trl + bitsandbytes (QLoRA)

Usage:
    NVIDIA_LIBS=$(find scripts/ft_env/.venv -path '*/nvidia/*/lib' -type d | paste -sd: -)
    LD_LIBRARY_PATH="$NVIDIA_LIBS" scripts/ft_env/.venv/bin/python scripts/dpo_train.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml
import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import DPOConfig, DPOTrainer


def parse_args():
    p = argparse.ArgumentParser(description="DPO fine-tuning (HF stack)")
    p.add_argument("--data", type=str, default="evals/sft_curated/dpo_honesty.yaml")
    p.add_argument("--out", type=str, default="models/dpo_gemma3_12b")
    p.add_argument("--base-model", type=str, default="google/gemma-3-12b-it")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--max-length", type=int, default=1024)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=16)
    p.add_argument("--beta", type=float, default=0.1)
    return p.parse_args()


def load_dpo_data(path: str) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    records = []
    for p in data.get("pairs", []):
        records.append({
            "prompt": p["input"].strip(),
            "chosen": p["chosen"].strip(),
            "rejected": p["rejected"].strip(),
        })
    return records


def main():
    args = parse_args()
    print(f"[dpo] Data: {args.data}")
    dpo_data = load_dpo_data(args.data)
    print(f"[dpo] Pairs: {len(dpo_data)}")

    # --- Quantization config ---
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # --- Load model ---
    print(f"[dpo] Loading {args.base_model} in 4bit...")
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # Gemma 3 + trl 1.0 workaround: disable token_type_ids requirement
    tokenizer.model_input_names = [n for n in tokenizer.model_input_names if n != "token_type_ids"]

    # --- LoRA ---
    print(f"[dpo] LoRA r={args.lora_r} alpha={args.lora_alpha}")
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # --- Dataset ---
    dataset = Dataset.from_list(dpo_data)

    # --- DPO ---
    print(f"[dpo] Training: epochs={args.epochs}, lr={args.lr}, beta={args.beta}")
    training_args = DPOConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_steps=2,
        logging_steps=1,
        save_strategy="epoch",
        fp16=False,
        bf16=True,
        optim="adamw_8bit",
        seed=42,
        beta=args.beta,
        max_length=args.max_length,
        remove_unused_columns=False,
        gradient_checkpointing=True,
    )

    trainer = DPOTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    print("[dpo] Starting...")
    trainer.train()
    print("[dpo] Training complete.")

    # --- Save LoRA ---
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out / "lora_adapter")
    tokenizer.save_pretrained(out / "lora_adapter")
    print(f"[dpo] Saved to {out / 'lora_adapter'}")

    # --- Quick test ---
    print("\n[dpo] Quick test...")
    test_prompt = "次のコードにバグはありますか？\ndef add(a, b): return a + b"
    inputs = tokenizer(test_prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out_ids = model.generate(**inputs, max_new_tokens=100)
    print(tokenizer.decode(out_ids[0], skip_special_tokens=True))
    print("\n[dpo] Done!")


if __name__ == "__main__":
    main()
