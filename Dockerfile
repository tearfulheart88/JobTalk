FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    MCP_HOST=0.0.0.0 \
    PORT=8000 \
    MCP_TRANSPORT=streamable-http \
    MOCK_MODE=true \
    LIVE_API_ENABLED=false \
    USAGE_DB_PATH=/app/data/usage.db

WORKDIR /app

COPY careertalk/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY careertalk/ .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health', timeout=3)" || exit 1

CMD ["python", "server.py"]
