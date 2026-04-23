# Shared AstroReason runtime with multiple agent CLIs installed side by side.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_TOOL_BIN_DIR=/usr/local/bin
ENV UV_TOOL_DIR=/usr/local/lib/uv/tools
ENV FACTORY_INSTALL_HOME=/usr/local/share/factory-home
ENV PATH="${FACTORY_INSTALL_HOME}/.factory/bin:/usr/local/bin:${PATH}"
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
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" \
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

RUN uv pip install --system \
    'brahe>=1.3.4' \
    'datasets>=4.8.4' \
    'huggingface-hub>=1.10.2' \
    'kagglehub[pandas-datasets]>=1.0.0' \
    'matplotlib>=3.10.8' \
    'numpy>=2.4.4' \
    'pyproj>=3.7.2' \
    'pyinstaller>=6.20,<7' \
    'pyyaml>=6.0.3' \
    'pytest>=9.0.3' \
    'shapely>=2.1.2' \
    'skyfield>=1.54'

RUN uv tool install --python 3.13 kimi-cli

RUN set -eux; \
    for cmd in claude codex gemini jq kimi opencode pi rg tree; do \
        command -v "$cmd"; \
    done; \
    command -v pyinstaller; \
    python -c "import brahe, datasets, huggingface_hub, kagglehub, matplotlib, numpy, pyproj, PyInstaller, yaml, pytest, shapely, skyfield" >/dev/null

WORKDIR /app/workspace

CMD ["/bin/bash"]
