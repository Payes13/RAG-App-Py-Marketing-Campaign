"""
Layer 6 — Prompt injection detection.

Scans user input before it reaches the LangChain Agent.
"""
import re

INJECTION_PATTERNS = [
    r"ignore (previous|all|prior) instructions",
    r"forget (your|all|the) rules",
    r"now act as",
    r"you are now",
    r"disregard (your|all|the)",
    r"pretend (you are|to be)",
    r"do not follow",
    r"override (your|the) (instructions|rules|prompt)",
    r"system prompt",
    r"jailbreak",
    r"\bDAN\b",
    r"\[INST\]",
    r"<\|im_start\|>",
]


def check_user_input(text: str) -> tuple[bool, str]:
    """
    Scan user input for prompt injection patterns.

    Returns:
        (True, "")                                    — input is clean
        (False, "Input contains disallowed content")  — injection detected

    The specific matched pattern is never disclosed to the caller.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Input contains disallowed content"
    return True, ""
