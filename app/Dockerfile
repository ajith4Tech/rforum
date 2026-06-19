# Build context: project root (rforum/)
# docker build -f app/Dockerfile -t rforum-api .

# ── Stage 1: install deps ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build
COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /workspace

RUN addgroup --system rforum && adduser --system --ingroup rforum rforum

COPY --from=builder /install /usr/local

# App package and alembic migrations
COPY app/ ./app/
COPY db/  ./db/

# Uploads directory (mounted as a volume in production)
RUN mkdir -p uploads && chown -R rforum:rforum /workspace

USER rforum

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
