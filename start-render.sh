#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
python tools/migrate_schema.py
exec python -m gunicorn config.wsgi:application --config gunicorn.conf.py
