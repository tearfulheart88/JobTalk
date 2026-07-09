FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001 \
    MCP_TRANSPORT=streamable-http

WORKDIR /app
COPY . /src

RUN set -eux; \
    if [ -f /src/careertalk/requirements.txt ]; then \
      cp -a /src/careertalk /app/careertalk; \
    elif [ -f /src/workspace/projects/careertalk_진로톡/careertalk/requirements.txt ]; then \
      cp -a /src/workspace/projects/careertalk_진로톡/careertalk /app/careertalk; \
    else \
      echo "CareerTalk source directory was not found."; \
      exit 1; \
    fi; \
    pip install --no-cache-dir --upgrade pip; \
    pip install --no-cache-dir -r /app/careertalk/requirements.txt

WORKDIR /app/careertalk
EXPOSE 8001

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8001", "--transport", "streamable-http"]
