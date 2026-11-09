FROM node:24-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG PUBLIC_ORIGIN
ARG PUBLIC_KEY
ENV VITE_API_BASE_URL=$PUBLIC_ORIGIN VITE_SUPABASE_URL=$PUBLIC_ORIGIN VITE_SUPABASE_PUBLISHABLE_KEY=$PUBLIC_KEY
RUN test -n "$PUBLIC_ORIGIN" && test -n "$PUBLIC_KEY" && npm run build \
    && node -e 'require("node:fs").writeFileSync("/build/public-config.json", JSON.stringify({origin:process.env.VITE_SUPABASE_URL,key:process.env.VITE_SUPABASE_PUBLISHABLE_KEY}))'

FROM public.ecr.aws/supabase/gotrue:v2.197.0 AS auth
FROM public.ecr.aws/supabase/postgrest:v16.5 AS rest
FROM python:3.13-alpine
RUN apk add --no-cache nginx ca-certificates && adduser -D -u 10001 sherlock
WORKDIR /app
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY --from=auth /usr/local/bin/auth /usr/local/bin/auth
COPY --from=rest /bin/postgrest /usr/local/bin/postgrest
COPY --from=frontend /build/frontend/dist /usr/share/nginx/html
COPY --from=frontend /build/public-config.json /app/public-config.json
COPY backend/src /app/backend/src
COPY deploy/northflank/nginx.conf.template /app/deploy/northflank/nginx.conf.template
ENV PYTHONPATH=/app/backend/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "sherlock_api.deployment", "portal"]
