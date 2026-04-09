"""Pre-execution safety guard for tool invocations.

Catches obvious destructive commands the Planner might still emit,
even after the system-prompt-level safety rules. Defense in depth.
"""
from __future__ import annotations

import re

# Patterns that should never be executed via shell_runner
_DANGEROUS_SHELL = [
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(\s|$)"),
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(-[a-zA-Z]*f[a-zA-Z]*\s+)?\.(\s|$)"),
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(-[a-zA-Z]*f[a-zA-Z]*\s+)?\$HOME"),
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(-[a-zA-Z]*f[a-zA-Z]*\s+)?~"),
    re.compile(r"\bmkfs\."),
    re.compile(r"\bdd\s+if="),
    re.compile(r":\(\)\s*\{.*:\|:&"),  # fork bomb
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r">\s*/dev/sda"),
    re.compile(r"\bchmod\s+-R\s+777\s+/"),
]

# File ops patterns
_DANGEROUS_PATHS = [
    re.compile(r"^/$"),
    re.compile(r"^/etc(/|$)"),
    re.compile(r"^/usr(/|$)"),
    re.compile(r"^/bin(/|$)"),
    re.compile(r"^/sbin(/|$)"),
    re.compile(r"^/boot(/|$)"),
    re.compile(r"^/sys(/|$)"),
    re.compile(r"^/proc(/|$)"),
]


class SafetyViolation(Exception):
    """Raised when a tool invocation is blocked by the safety guard."""


def check_shell_command(command: str) -> None:
    for pat in _DANGEROUS_SHELL:
        if pat.search(command):
            raise SafetyViolation(
                f"blocked by safety guard: matches {pat.pattern!r}"
            )


def check_file_path(path: str) -> None:
    for pat in _DANGEROUS_PATHS:
        if pat.match(path):
            raise SafetyViolation(
                f"blocked by safety guard: dangerous path {path!r}"
            )


def check_step(tool_name: str, args: dict) -> None:
    """Inspect a planned step before execution. Raises on danger."""
    if tool_name == "shell_runner":
        cmd = args.get("command", "")
        check_shell_command(cmd)
    elif tool_name == "file_ops":
        path = args.get("path", "")
        if path:
            check_file_path(path)
        # also check write content for embedded shell-out (best effort)
    elif tool_name == "code_executor":
        code = args.get("code", "")
        # block obvious shell-outs from code
        if "os.system" in code or "subprocess" in code:
            for pat in _DANGEROUS_SHELL:
                if pat.search(code):
                    raise SafetyViolation(
                        f"blocked by safety guard: code contains dangerous pattern"
                    )
