FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr curl ffmpeg && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 app
WORKDIR /app
COPY backend/requirements-local.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt pytesseract
COPY backend/ .
RUN mkdir -p /app/storage && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -fs http://localhost:8000/health || exit 1
# Migrations are an explicit step: docker compose run --rm backend alembic upgrade head
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
