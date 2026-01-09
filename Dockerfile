FROM ubuntu:latest

ARG USERNAME=richard
ARG PYTHON_VERSION=3.14

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/venv/bin:$PATH" \
    VIRTUAL_ENV=/home/${USERNAME}/venv

# Install dependencies, Node.js, and create user in single layer
RUN apt-get update && apt-get install -y curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_current.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash ${USERNAME}

# Copy dist folder (may contain wheel file)
COPY dist* /tmp/dist/

# Switch to user and set up environment
USER ${USERNAME}
WORKDIR /home/${USERNAME}

# Install uv, Python, create venv, install rtube, and run npm install
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv python install ${PYTHON_VERSION} \
    && uv venv --python ${PYTHON_VERSION} /home/${USERNAME}/venv \
    && if ls /tmp/dist/*.whl 1>/dev/null 2>&1; then \
           uv pip install /tmp/dist/*.whl; \
       else \
           uv pip install rtube; \
       fi \
    && cd /home/${USERNAME}/venv/lib/python${PYTHON_VERSION}/site-packages/rtube/static \
    && npm install

CMD [".venv/bin/flask", "--app", "rtube", "run"]
