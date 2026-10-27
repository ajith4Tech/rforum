# Pinned by digest: an unpinned tag re-resolves on every build, and each
# upstream republish of python:3.12-slim invalidates every layer below —
# including the multi-minute LibreOffice apt layer. Bump deliberately
# (docker buildx imagetools inspect python:3.12-slim) to pick up patches.
FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f

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

# Runs as a non-root user; writable dirs (LibreOffice profile under $HOME,
# temp conversion dir, local storage fallback root) are supplied as emptyDir/
# PVC mounts by the Helm chart, not baked into the image.
# Ownership is set by COPY --chown instead of a trailing `chown -R /srv`,
# which re-wrote every copied file into an extra duplicate layer.
RUN useradd --create-home --uid 10001 rforum \
    && chown rforum:rforum /srv /srv/app
COPY --chown=rforum:rforum app/ app/
COPY --chown=rforum:rforum db/ db/
COPY --chown=rforum:rforum scripts/ scripts/
USER rforum
ENV HOME=/home/rforum

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
