FROM python:3.12-slim

WORKDIR /app

# System dependencies:
#   libreoffice-headless — PPT/PPTX → PDF conversion
#   libmagic1            — server-side MIME type detection (python-magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-headless \
        libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
