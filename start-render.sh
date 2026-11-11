#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
export APP_ENVIRONMENT=production
unset APP_USE_DIRECT_DATABASE DATABASE_URL_UNPOOLED PGPASSWORD PGSERVICE PGSERVICEFILE PGPASSFILE
: "${DATABASE_URL:?Defina a conexão PostgreSQL da aplicação no ambiente do Render.}"
python manage.py check --deploy --fail-level WARNING
python tools/check_runtime_database.py
exec python -m gunicorn config.wsgi:application --config gunicorn.conf.py
