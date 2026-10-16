# ADR 001: Model Selection for CanaryNet Lite LLM Fallback

## Status
Decided

## Date
2026-10-16

## Context
CanaryNet Lite runs on local developer hardware (Windows 11, Intel i5-1155G7, 12 GB RAM, CPU-only, no GPU).
Unknown visitor commands must be handled with realistic Linux terminal output and valid state changes under strict latency limits (<20s timeout, target <2-3s response) without paid APIs or outbound network traffic.

## Evaluated Models
1. **Qwen2.5 1.5B** (`qwen2.5:1.5b`)
   - **Ollama tag**: `qwen2.5:1.5b`
   - **Licence**: Apache 2.0 (per Alibaba Qwen open-weight model card; permissive, commercial and lab use allowed)
   - **Parameter Size**: 1.54B parameters (Q4_K_M ~986 MB)
2. **Qwen2.5 0.5B** (`qwen2.5:0.5b`) [Fallback evaluation]
   - **Ollama tag**: `qwen2.5:0.5b`
   - **Licence**: Apache 2.0
   - **Parameter Size**: ~0.5B parameters (~398 MB)

## Shootout Results (Measured CPU Inference)
- **Model Evaluated**: `qwen2.5:1.5b`
- **Prompts Tested**: 10
- **Valid JSON Schema Pass Rate**: 7/10 (70.0%) — Note: verbose command outputs (such as `ps aux` and `netstat -tuln`) exceeded token limits when capped at 256 tokens, truncating JSON syntax; concise commands achieved 100% compliance.
- **Average Tokens / Second**: 17.39 tps
- **Average Time to First Token (TTFT)**: 0.297 s

## Decision
We select **Qwen2.5 1.5B** (`qwen2.5:1.5b`) as the primary decoy model, with **Qwen2.5 0.5B** (`qwen2.5:0.5b`) as an immediate fallback if CPU thermal throttling or memory pressure causes latency to exceed 3.0s.

## Consequences & Honest Limitations
- JSON schema enforcement (`format=SCHEMA`) significantly constrains output format, but does not guarantee 100% valid JSON if token generation is truncated before closing braces. The validator (`canarynet.llm.validator`) must parse and validate all proposed state changes.
- Binding services strictly to `127.0.0.1` and restricting outbound calls to loopback Ollama (`127.0.0.1:11434`) prevents non-loopback exposure, but host safety also relies on never executing visitor input (enforced by `tests/test_safety.py`).
- The benchmark comparison is strictly against a "last-10-command baseline", not Cowrie itself.
- The prompt injection guard is a rule-based perimeter with a defined test set, not a formal security guarantee.
