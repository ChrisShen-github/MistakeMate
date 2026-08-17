#!/bin/sh
set -eu

mkdir -p /app/storage
nginx_pid=""
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

stop_children() {
  kill -TERM "$backend_pid" 2>/dev/null || true
  kill -TERM "$nginx_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
  wait "$nginx_pid" 2>/dev/null || true
}

nginx -g 'daemon off;' &
nginx_pid=$!
trap 'stop_children; exit 0' INT TERM

# Nginx can continue serving the frontend after Uvicorn has crashed, which
# otherwise leaves every API request returning 502 forever.  End this
# container when either process exits so Docker's restart policy can recover it.
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 1
done

stop_children
exit 1
