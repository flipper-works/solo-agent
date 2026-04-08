# NOTICE

This repository contains **source code only**. It does NOT redistribute any
LLM model weights. Users must obtain models separately and comply with each
model's respective license.

---

## Source Code License

The source code in this repository is licensed under the **MIT License**
(see [LICENSE](LICENSE)).

## Third-Party Model Licenses

This project is designed to interoperate with the following models. When you
download and run any of these models, **you are bound by their licenses**, not
this repository's MIT license.

### Google Gemma 3 (default model)

- License: [Gemma Terms of Use](https://ai.google.dev/gemma/terms)
- Prohibited Use Policy: [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy)
- Notes:
  - Permits use, modification, and redistribution under the Gemma Terms.
  - Any "Model Derivatives" you create must propagate the Gemma Terms.
  - You must comply with the Prohibited Use Policy.

### Llama 3.1 Swallow (Tokyo Tech, optional)

This is a continual-pretrained derivative of Meta Llama 3.1.

- Base license: [Llama 3.1 Community License](https://llama.meta.com/llama3_1/license/)
- Acceptable Use Policy: [Llama 3.1 AUP](https://llama.meta.com/llama3_1/use-policy/)
- Built with Llama. The model name "Llama-3.1-Swallow" preserves the required
  "Llama" prefix per the Llama 3.1 Community License.
- Notes:
  - Free for organizations with under 700M monthly active users.
  - Any redistribution of derivatives must include the Llama license, AUP,
    and an attribution notice ("Built with Llama").

### Other Models

Any other model you load via Ollama or directly is subject to its own license
(Mistral Apache-2.0, Qwen Apache-2.0, etc.). Check before redistributing.

---

## Safety & Liability Notice

This project includes tools that execute arbitrary shell commands and Python
code on the host machine (`shell_runner`, `code_executor`). These tools are
**NOT sandboxed** in Phase 1.

- **Run only on machines you own and trust.**
- **Do not expose this agent to untrusted user input** (e.g., the public
  internet) without first implementing proper sandboxing (Docker isolation,
  seccomp, network egress controls — see Phase 2/3 plans in README).
- The maintainers accept no liability for damage caused by misuse or by
  prompt-injection attacks against the agent.

By using this software, you accept responsibility for its operation in your
environment.
