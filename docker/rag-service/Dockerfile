FROM python:3.12-slim
WORKDIR /app
COPY src/requirements/base.txt requirements/base.txt
COPY src/requirements/rag.txt requirements/rag.txt
RUN pip install --no-cache-dir -r requirements/rag.txt
COPY src/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8003
CMD ["uvicorn", "agentic_backend.api.rag_app:app", "--host", "0.0.0.0", "--port", "8003"]
