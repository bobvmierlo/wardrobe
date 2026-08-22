# ---- Stage 1: build the frontend ----
FROM node:26-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WARDROBE_DATA_DIR=/data

WORKDIR /app

# System deps for Pillow are already present in the slim image for JPEG/PNG.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend source.
COPY backend/app ./app

# Built frontend, served by FastAPI from ./static.
COPY --from=frontend /build/dist ./static

# Persistent data (SQLite database + uploaded photos).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Single worker keeps SQLite writes simple; plenty for household use.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
