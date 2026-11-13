FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt fastapi==0.115.6 uvicorn==0.32.1
COPY engine engine
COPY web web
WORKDIR /app/engine
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "xahoo.api:app", "--host", "0.0.0.0", "--port", "8000"]
