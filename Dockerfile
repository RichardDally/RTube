# ==========================================
# Build Stage
# ==========================================
FROM ubuntu:24.04 AS builder

ARG USERNAME=richard
ARG PYTHON_VERSION=3.14

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/venv/bin:$PATH" \
    VIRTUAL_ENV=/home/${USERNAME}/venv

# Install build dependencies, Node.js, ffmpeg, and create user
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils \
    && curl -fsSL https://deb.nodesource.com/setup_current.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && curl -fsSL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && mv /tmp/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ \
    && mv /tmp/ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ffmpeg* \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash ${USERNAME}

# Copy dist folder
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


# ==========================================
# Target Stage
# ==========================================
FROM ubuntu:24.04

ARG USERNAME=richard

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/venv/bin:$PATH" \
    VIRTUAL_ENV=/home/${USERNAME}/venv

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash ${USERNAME}

# Copy ffmpeg/ffprobe binaries from builder
COPY --from=builder /usr/local/bin/ffmpeg /usr/local/bin/
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/

# Copy the uv installation, python download, and the fully prepared virtual environment
COPY --from=builder --chown=${USERNAME}:${USERNAME} /home/${USERNAME}/.local /home/${USERNAME}/.local
COPY --from=builder --chown=${USERNAME}:${USERNAME} /home/${USERNAME}/venv /home/${USERNAME}/venv

# Switch to user for runtime
USER ${USERNAME}
WORKDIR /home/${USERNAME}

CMD ["venv/bin/gunicorn", "--bind", "0.0.0.0:5000", "rtube:create_app()"]
