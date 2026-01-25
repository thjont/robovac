FROM ghcr.io/home-assistant/devcontainer:2-addons

# Add GitHub CLI repository
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# Add Node.js repository
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -

# Install all apt packages in one layer
RUN apt-get update && \
    apt-get install -y \
        gh \
        nodejs \
        protobuf-compiler \
        xxd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install go-task
RUN sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install markdownlint-cli2 (requires Node.js)
RUN npm install -g markdownlint-cli2
