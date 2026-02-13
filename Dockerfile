# Backend service container for Railway
FROM python:3.12-slim

WORKDIR /app

# Install backend dependencies
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source so module path `app.*` resolves
COPY app /app/app

# Static/uploads directory expected by the app
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
