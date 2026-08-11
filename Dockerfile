FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY docker/start.sh /app/start.sh
COPY docker/nginx.conf /etc/nginx/sites-enabled/default
COPY --from=frontend-build /build/frontend/dist /usr/share/nginx/html

RUN mkdir -p /app/storage && chmod +x /app/start.sh

EXPOSE 8080
CMD ["/app/start.sh"]
