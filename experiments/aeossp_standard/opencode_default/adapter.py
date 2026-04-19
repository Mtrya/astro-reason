#!/usr/bin/env python3
"""OpenCode experiment-owned adapter."""

from __future__ import annotations


NAME = "opencode"
CONFIG_TARGET_DIR = "/root/.config/opencode"
SESSION_LOG_TARGET_DIR = "/root/.local/share/opencode"
INTERACTIVE_COMMAND = ("/bin/bash", "-i")


def build_headless_command(task_prompt: str) -> list[str]:
    return ["opencode", "run", task_prompt]
