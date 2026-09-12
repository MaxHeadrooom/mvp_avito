#!/bin/sh
set -eu

python app/seed.py
export ESTABLISHMENT_ID="$(python -c "import json; print(json.load(open('/app/establishment_id.json'))['establishment_id'])")"
echo "Starting establishment-service for establishment_id=$ESTABLISHMENT_ID"
exec python app/main.py

