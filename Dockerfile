# Railway (and other PaaS): API and Worker share this image; override CMD per service.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web_api ./web_api
COPY video_auto_cut ./video_auto_cut

# Default: run API (Railway sets PORT; override Start Command for Worker to: python -m web_api)
EXPOSE 8000
CMD ["sh", "-c", "uvicorn web_api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
