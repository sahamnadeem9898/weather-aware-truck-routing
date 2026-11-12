# One image for the whole app: build the React bundle, then serve it and the
# API from Django (WhiteNoise + gunicorn).

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Run as an unprivileged user.
RUN useradd --system --no-create-home --uid 10001 app
USER app

# One worker keeps the in-memory caches shared by every request, and fits the
# free tier's 512 MB. Threads give concurrency because the work is mostly
# waiting on third-party APIs.
CMD ["sh", "-c", "gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120"]
