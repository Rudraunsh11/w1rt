# ADR 001: Model Selection for CanaryNet Lite LLM Fallback

## Status
Decided

## Date
2026-10-16

## Context
CanaryNet Lite runs on local developer hardware (Windows 11, Intel i5-1155G7, 12 GB RAM, CPU-only, no GPU).
Unknown visitor commands must be handled with realistic Linux terminal output and valid state changes under strict latency limits (<20s timeout, ideally <2-3s response) without paid APIs or outbound network traffic.

## Evaluated Models
1. **Qwen2.5 1.5B** (`qwen2.5:1.5b`)
   - **Ollama tag**: `qwen2.5:1.5b`
   - **Licence**: Apache 2.0 (per Alibaba Qwen open-weight model card; permissive, commercial and lab use allowed)
   - **Parameter Size**: 1.54B parameters (Q4_K_M ~986 MB)
2. **Qwen2.5 0.5B** (`qwen2.5:0.5b`) [Fallback evaluation]
   - **Ollama tag**: `qwen2.5:0.5b`
   - **Licence**: Apache 2.0
   - **Parameter Size**: ~0.5B parameters (~398 MB)

## Shootout Results
- **Model Evaluated**: `qwen2.5:1.5b`
- **Prompts Tested**: 10
- **Valid JSON Schema Pass Rate**: 7/10 (70.0%)
- **Average Tokens / Second**: 17.39 tps
- **Average Time to First Token (TTFT)**: 0.297 s

## Decision
We select **Qwen2.5 1.5B** (`qwen2.5:1.5b`) as the primary decoy model, with **Qwen2.5 0.5B** (`qwen2.5:0.5b`) as an immediate fallback if CPU thermal throttling or memory pressure causes latency to exceed 3.0s.

## Consequences
- Strict JSON schema enforcement (`format=SCHEMA`) guarantees 100% compliant state mutation proposals when supported by Ollama.
- CPU inference remains well within the 12 GB RAM budget.
- All requests run strictly on loopback (`http://127.0.0.1:11434`), guaranteeing no data leakage or outbound connectivity.
