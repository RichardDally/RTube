FROM ubuntu:latest

ARG USERNAME=richard
ARG PYTHON_VERSION=3.14

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/venv/bin:$PATH" \
    VIRTUAL_ENV=/home/${USERNAME}/venv

# Install dependencies, Node.js, ffmpeg, and create user in single layer
RUN apt-get update && apt-get install -y curl ca-certificates xz-utils \
    && curl -fsSL https://deb.nodesource.com/setup_current.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && mv /tmp/ffmpeg-release-amd64-static/ffmpeg /usr/local/bin/ \
    && mv /tmp/ffmpeg-release-amd64-static/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ffmpeg* \
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

CMD ["venv/bin/gunicorn", "--bind", "0.0.0.0:5000", "rtube:create_app()"]
