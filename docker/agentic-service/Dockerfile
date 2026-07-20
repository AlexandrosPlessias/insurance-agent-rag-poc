FROM python:3.12-slim
WORKDIR /app
COPY src/requirements/base.txt requirements/base.txt
COPY src/requirements/agentic.txt requirements/agentic.txt
RUN pip install --no-cache-dir -r requirements/agentic.txt
COPY src/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8002
CMD ["uvicorn", "agentic_backend.api.agentic_app:app", "--host", "0.0.0.0", "--port", "8002"]
