FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.lock /app/backend-requirements.lock
COPY ml/requirements.lock /app/ml-requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/backend-requirements.lock -r /app/ml-requirements.lock
COPY backend/src /app/backend/src
COPY ml/src /app/ml/src
ENV PYTHONPATH=/app/backend/src:/app/ml/src
ENV MODEL_ARTIFACT_DIR=/models
USER 65532:65532
CMD ["python", "-m", "sherlock_api.detection.cli", "run"]
