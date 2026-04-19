# Shared AstroReason runtime with multiple agent CLIs installed side by side.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.local/bin:/root/.factory/bin:/usr/local/bin:${PATH}"
ENV DISABLE_AUTOUPDATER=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    coreutils \
    curl \
    git \
    gnupg \
    jq \
    less \
    ripgrep \
    tree \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g \
    @anthropic-ai/claude-code \
    @google/gemini-cli \
    @mariozechner/pi-coding-agent \
    @openai/codex \
    opencode-ai

RUN uv tool install --python 3.13 kimi-cli

RUN curl -fsSL https://app.factory.ai/cli | sh

RUN command -v claude >/dev/null \
    && command -v codex >/dev/null \
    && command -v droid >/dev/null \
    && command -v gemini >/dev/null \
    && command -v jq >/dev/null \
    && command -v kimi >/dev/null \
    && command -v opencode >/dev/null \
    && command -v pi >/dev/null \
    && command -v rg >/dev/null \
    && command -v tree >/dev/null

WORKDIR /app/workspace

CMD ["/bin/bash"]
