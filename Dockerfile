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

# Switch to user and set up environment
USER ${USERNAME}
WORKDIR /home/${USERNAME}

# Install uv, Python, create venv, install rtube, and run npm install
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv python install ${PYTHON_VERSION} \
    && uv venv --python ${PYTHON_VERSION} /home/${USERNAME}/venv \
    && uv pip install rtube \
    && cd /home/${USERNAME}/venv/lib/python${PYTHON_VERSION}/site-packages/rtube/static && npm install

EXPOSE 5000

CMD ["python", "-m", "rtube"]
