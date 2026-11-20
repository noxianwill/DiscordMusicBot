FROM python:3.11-slim

# Install system dependencies: FFmpeg, curl, git, and unzip
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno for YouTube challenge solving
RUN curl -fsSL https://deno.land/install.sh | sh && \
    cp /root/.deno/bin/deno /usr/local/bin/deno

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "launcher.py"]
