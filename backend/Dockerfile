FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/src ./src
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home sherlock
USER sherlock
EXPOSE 8000
CMD ["uvicorn", "sherlock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
