# API container for the AI-OS.
# Build: docker compose up --build
FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

# Drop root before running: this image is the internet-facing app container
# (unlike Dockerfile.executor's already-sandboxed backend), so a container
# compromise here must not hand out root for free. Reuses the same nobody
# uid/gid Dockerfile.executor already runs as, and chowns /app (including the
# AIOS_DATA_DIR mount point at /app/data) so the dropped-privilege process can
# still read/write its own data.
RUN chown -R 65534:65534 /app
USER 65534:65534

EXPOSE 8000

CMD ["python", "-m", "aios"]
