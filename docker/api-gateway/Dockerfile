FROM python:3.12-slim
WORKDIR /app
COPY src/requirements/base.txt requirements/base.txt
COPY src/requirements/agentic.txt requirements/agentic.txt
COPY src/requirements/gateway.txt requirements/gateway.txt
RUN pip install --no-cache-dir -r requirements/gateway.txt
COPY src/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "agentic_backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
