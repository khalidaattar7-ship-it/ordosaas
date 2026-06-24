# --- Stage 1: build the React frontend ---
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY ordosaas/frontend/package*.json ./
RUN npm ci
COPY ordosaas/frontend/ .
RUN npm run build

# --- Stage 2: backend + bundled frontend ---
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY ordosaas/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ordosaas/backend/ .
COPY --from=frontend-build /frontend/dist ./frontend_dist
RUN chmod +x start.sh

EXPOSE 8000
CMD ["bash", "start.sh"]
