FROM python:3.12-slim
WORKDIR /app
# ffmpeg required by faster-whisper to decode browser audio (WebM/Opus)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY src/requirements/base.txt requirements/base.txt
COPY src/requirements/voice.txt requirements/voice.txt
RUN pip install --no-cache-dir -r requirements/voice.txt
COPY src/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["uvicorn", "agentic_backend.api.voice_app:app", "--host", "0.0.0.0", "--port", "8001"]
