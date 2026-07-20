FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY src/requirements/base.txt requirements/base.txt
COPY src/requirements/ingestion.txt requirements/ingestion.txt
RUN pip install --no-cache-dir -r requirements/ingestion.txt
COPY src/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8004
CMD ["uvicorn", "agentic_backend.api.ingestion_app:app", "--host", "0.0.0.0", "--port", "8004"]
