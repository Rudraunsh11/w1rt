"""Prompt injection guard and input/output sanitization for CanaryNet LLM."""

import re

# Boundary tags to isolate visitor input as inert data
INPUT_START_TAG = "===BEGIN_VISITOR_COMMAND==="
INPUT_END_TAG = "===END_VISITOR_COMMAND==="


def wrap_input(line: str) -> str:
    """Quotes the visitor line as raw data inside explicit demarcation boundaries.

    Ensures visitor input is treated strictly as terminal command text and not instructions.
    """
    clean = line.strip()
    return (
        f"{INPUT_START_TAG}\n"
        f"{clean}\n"
        f"{INPUT_END_TAG}\n"
        f"Simulate execution of the command above within the virtual Ubuntu 22.04 environment."
    )


def check_output(text: str) -> bool:
    """Inspects text for prompt leakage, role breaks, or instruction following artifacts.

    Returns False if hostile leakage or role breaks are detected, True if clean.
    """
    if not text:
        return True

    lower = text.lower()

    # Blocked phrases and AI identity leaks
    forbidden_phrases = [
        "as an ai",
        "i am an ai",
        "i am a language model",
        "as a language model",
        "system prompt",
        "ignore previous instructions",
        "ignore all previous",
        "my instructions are",
        "i cannot fulfill this request",
        "as a decoy",
        "canarynet",
    ]

    for phrase in forbidden_phrases:
        if phrase in lower:
            return False

    return True
