FROM python:3.12-slim

# Build context is the repository root (docker build -f app/Dockerfile .),
# not app/ — required so "app" resolves as a real Python package under
# WORKDIR and `uvicorn app.main:app` (below) can import it, and so the
# image also has db/ (Alembic migrations) and scripts/ (cleanup/migration
# one-shots) available.
WORKDIR /srv

# System dependencies:
#   libreoffice-impress-nogui/-writer-nogui — PPT/PPTX/DOC/DOCX/ODP/ODT → PDF
#     conversion (headless). Debian's "libreoffice-headless" metapackage from
#     bookworm no longer exists in trixie (the current python:3.12-slim base)
#     — it was split into per-component "-nogui" packages; these two pull in
#     libreoffice-core-nogui as a transitive dependency and still provide the
#     `libreoffice`/`soffice` binaries app/services/file_processing.py looks for.
#   libmagic1 — server-side MIME type detection (python-magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress-nogui \
        libreoffice-writer-nogui \
        libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# requirements.txt's moto entry is test-only (mocks S3 for
# tests/test_s3_storage_backend.py) — excluded here so it and its
# dependencies aren't installed into the production image.
COPY app/requirements.txt app/requirements.txt
RUN grep -v '^moto' app/requirements.txt > /tmp/requirements-prod.txt \
    && pip install --no-cache-dir -r /tmp/requirements-prod.txt \
    && rm /tmp/requirements-prod.txt

COPY app/ app/
COPY db/ db/
COPY scripts/ scripts/

# Runs as a non-root user; writable dirs (LibreOffice profile under $HOME,
# temp conversion dir, local storage fallback root) are supplied as emptyDir/
# PVC mounts by the Helm chart, not baked into the image.
RUN useradd --create-home --uid 10001 rforum \
    && chown -R rforum:rforum /srv
USER rforum
ENV HOME=/home/rforum

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
