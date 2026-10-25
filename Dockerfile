FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md constraints.txt ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir -c constraints.txt .

COPY tests ./tests
COPY scripts ./scripts
COPY paper ./paper
COPY docs ./docs

RUN mkdir -p data/raw data/processed results/figures results/tables

CMD ["python", "-m", "fakealpha", "--help"]
