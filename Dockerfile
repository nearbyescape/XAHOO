FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
# requirements.lock pins every package (incl. dependencies), so pip never has to search the index for versions.
COPY engine/requirements.lock engine/requirements.lock
RUN pip install --prefer-binary -r engine/requirements.lock
COPY engine engine
COPY web web
WORKDIR /app/engine
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "xahoo.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
