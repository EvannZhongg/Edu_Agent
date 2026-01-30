FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY worker.py /app/services/analyzer/worker.py
ENV PYTHONPATH=/app
CMD ["celery", "-A", "services.analyzer.worker", "worker", "--loglevel=info", "--queues=analyze_task"]
