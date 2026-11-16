# XAHOO direction probability terminal: build the screen with Node, run the server on Python.
# Build on the VPS with:  docker build --network=host -t xahoo:latest .
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=60 PIP_RETRIES=10 PIP_DISABLE_PIP_VERSION_CHECK=1
# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server/requirements.lock server/requirements.lock
RUN pip install -r server/requirements.lock
COPY server/xahoo server/xahoo
COPY models models
COPY --from=web /web/dist web/dist
RUN useradd --system --uid 10001 xahoo && mkdir -p /data && chown xahoo /data
USER xahoo
ENV XAHOO_MODE=live XAHOO_DATA=/data
WORKDIR /app/server
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/robots.txt', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "uvicorn", "xahoo.app:app", "--host", "0.0.0.0", "--port", "8010", "--proxy-headers", "--forwarded-allow-ips", "*", "--log-level", "info"]
