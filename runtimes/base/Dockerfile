# Shared AstroReason runtime with multiple agent CLIs installed side by side.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_TOOL_BIN_DIR=/usr/local/bin
ENV UV_TOOL_DIR=/usr/local/lib/uv/tools
ENV FACTORY_INSTALL_HOME=/usr/local/share/factory-home
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk
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
    openjdk-17-jre-headless \
    ripgrep \
    tree \
    vim-tiny \
    && ln -sfn /usr/lib/jvm/java-17-openjdk-$(dpkg --print-architecture) "$JAVA_HOME" \
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
    'bsk==2.9.0' \
    'brahe==1.4.2' \
    'datasets==4.8.4' \
    'huggingface-hub==1.12.0' \
    'kagglehub[pandas-datasets]==1.0.0' \
    'matplotlib==3.10.7' \
    'networkx==3.6.1' \
    'numpy==2.2.6' \
    'orekit-jpype==13.1.4.0' \
    'ortools==9.15.6755' \
    'pandas==2.3.3' \
    'plotly==6.7.0' \
    'pulp==3.3.0' \
    'pydantic==2.13.3' \
    'pygmo==2.19.8' \
    'pyproj==3.7.2' \
    'pyinstaller==6.20.0' \
    'pyyaml==6.0.3' \
    'pytest==9.0.3' \
    'scikit-learn==1.8.0' \
    'scipy==1.17.1' \
    'shapely==2.1.2' \
    'skyfield==1.54' \
    'sympy==1.14.0' \
    'tqdm==4.67.1'

RUN uv tool install --python 3.13 kimi-cli

RUN set -eux; \
    for cmd in claude codex gemini jq kimi opencode pi rg tree; do \
        command -v "$cmd"; \
    done; \
    java -version; \
    command -v pyinstaller; \
    python -c "import Basilisk, brahe, datasets, huggingface_hub, kagglehub, matplotlib, networkx, numpy, orekit_jpype, ortools, pandas, plotly, pulp, pydantic, pygmo, pyproj, PyInstaller, scipy, shapely, sklearn, skyfield, sympy, tqdm, yaml, pytest" >/dev/null; \
    python -c "import orekit_jpype as orekit; orekit.initVM(); from org.orekit.time import AbsoluteDate; assert AbsoluteDate.J2000_EPOCH is not None"

WORKDIR /app/workspace

CMD ["/bin/bash"]
