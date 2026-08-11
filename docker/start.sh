#!/bin/sh
set -eu

mkdir -p /app/storage
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

shutdown() {
  kill -TERM "$backend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
  exit 0
}

trap shutdown INT TERM
nginx -g 'daemon off;' &
nginx_pid=$!
wait "$nginx_pid"
shutdown
