#!/bin/sh
# Worker container entrypoint.
# Hugging Face Docker Spaces expect an HTTP listener on $PORT (default 7860) to
# consider the Space healthy — serve a trivial one alongside the Celery worker.
mkdir -p /tmp/health && echo "worker alive" > /tmp/health/index.html
python -m http.server "${PORT:-7860}" --directory /tmp/health &

exec celery -A worker.tasks worker \
  --loglevel=info \
  --concurrency="${CELERY_CONCURRENCY:-2}"
