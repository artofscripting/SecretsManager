FROM python:3.12-slim

WORKDIR /workspace

# Build dependencies for cryptography wheels/source when needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY linux_cli/requirements.txt /workspace/linux_cli/requirements.txt
RUN pip install --no-cache-dir -r /workspace/linux_cli/requirements.txt

COPY . /workspace

WORKDIR /workspace/linux_cli
RUN python build_binary.py
