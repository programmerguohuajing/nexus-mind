FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NEXUSMIND_RUNTIME=docker
ENV NEXUSMIND_DATA_ROOT=/data
ENV NEXUSMIND_HOST=0.0.0.0
ENV NEXUSMIND_PORT=8301

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git config --system --add safe.directory '*' \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md README_CN.md USER_MANUAL.md USER_MANUAL_CN.md LICENSE ./
COPY src ./src
COPY scripts ./scripts

RUN pip install --no-cache-dir ".[local]"

EXPOSE 8301

CMD ["python", "scripts/vault_service.py"]
