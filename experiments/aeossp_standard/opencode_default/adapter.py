#!/usr/bin/env python3
"""OpenCode experiment-owned adapter."""

from __future__ import annotations


NAME = "opencode"
CONFIG_TARGET_DIR = "/tmp/astroreason-xdg-config/opencode"
SESSION_LOG_TARGET_DIR = "/tmp/astroreason-xdg-data/opencode"
INTERACTIVE_COMMAND = ("/bin/bash", "-i")


def build_headless_command(task_prompt: str) -> list[str]:
    return ["opencode", "run", "--dangerously-skip-permissions", task_prompt]
