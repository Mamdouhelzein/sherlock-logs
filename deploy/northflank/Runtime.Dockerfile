FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.lock /tmp/backend-requirements.lock
COPY ml/requirements.lock /tmp/ml-requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/backend-requirements.lock -r /tmp/ml-requirements.lock
COPY backend/src /app/backend/src
COPY ml/src /app/ml/src
COPY tools/beta_cleanup.py /app/tools/beta_cleanup.py
COPY deploy/northflank/fetch_model.py /app/fetch_model.py
# The public release contains only the original synthetic v1 model, not events,
# account records, local settings or credentials. Every file is checksum pinned.
RUN python /app/fetch_model.py
ENV PYTHONPATH=/app/backend/src:/app/ml/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home sherlock
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "sherlock_api.deployment", "runtime"]
