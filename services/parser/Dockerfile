FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY worker.py /app/services/parser/worker.py
ENV PYTHONPATH=/app
CMD ["celery", "-A", "services.parser.worker", "worker", "--loglevel=info", "--queues=parse_task"]
