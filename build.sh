#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
export APP_ENVIRONMENT=production
unset APP_USE_DIRECT_DATABASE DATABASE_URL_UNPOOLED PGPASSWORD PGSERVICE PGSERVICEFILE PGPASSFILE
python -m pip install -r requirements.txt
python -m pip check
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
