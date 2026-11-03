#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
python -m pip install -r requirements.txt
python -m pip check
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
