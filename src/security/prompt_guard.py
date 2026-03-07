"""
Layer 6 — Prompt injection detection.

The CLAUDE.md documents 6 security layers for this app. Layers 1–5 protect the SQL pipeline (whitelist, regex blocklist, complexity limits, timeout, log masking). Layer 6 is the only one that protects the LLM — it scans the raw user text before it ever reaches the AI agent. The goal: prevent a user from hijacking the AI's behavior by embedding instructions in their request fields.

Scans user input before it reaches the LangChain Agent.
"""
import re

# The r"..." prefix means raw string — backslashes are not treated as escape characters, so \b stays \b (a word boundary), not a backspace.
INJECTION_PATTERNS = [
    # "ignore previous instructions", "ignore all instructions"
    r"ignore (previous|all|prior) instructions",
    # "forget your rules", "forget all rules"
    r"forget (your|all|the) rules",
    # "now act as", "you are now"
    r"now act as",
    r"you are now",
    # "disregard your rules", "disregard all rules"
    r"disregard (your|all|the)",
    # "pretend you are", "pretend to be"
    r"pretend (you are|to be)",
    # "do not follow", "do not obey"
    r"do not follow",
    # "override your instructions", "override your rules"
    r"override (your|the) (instructions|rules|prompt)",
    # "system prompt"
    r"system prompt",
    # "jailbreak"
    r"jailbreak",
    # "DAN" (Dark Angel Network)
    r"\bDAN\b",
    # "[INST]" (LLM instruction tags). [INST] tag used by Llama/Mistral models to inject system prompts
    r"\[INST\]",
    # "


def check_user_input(text: str) -> tuple[bool, str]:
    """
    Scan user input for prompt injection patterns.

    Returns:
        (True, "")                                    — input is clean
        (False, "Input contains disallowed content")  — injection detected

    The specific matched pattern is never disclosed to the caller.
    """
    for pattern in INJECTION_PATTERNS:
        # re.search scans the entire string looking for any match anywhere (unlike re.match which only checks the start). Returns a match object if found, None if not — so it's truthy/falsy:
        # re.IGNORECASE makes it case-insensitive — catches "JAILBREAK", "JailBreak", etc.
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Input contains disallowed content"
    return True, ""
