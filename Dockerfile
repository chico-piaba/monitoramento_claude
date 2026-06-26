FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LM_CLASSIFIER_ENABLED=1 \
    LM_CLASSIFY_ONLY_ATTENTION=1 \
    LM_CLASSIFIER_TIMEOUT_S=3.0 \
    LMSTUDIO_BASE=http://host.docker.internal:1234/v1 \
    LMSTUDIO_CHAT_URL=

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000

CMD ["python", "pi_monitor_dashboard.py"]
