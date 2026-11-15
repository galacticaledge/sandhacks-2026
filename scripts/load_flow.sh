#!/bin/sh
# Load the USIBWC river-flow history (gauge 11-0133.00) into the database.
# Note: the collector accepts the USIBWC Water Data Portal disclaimer on your behalf.
# Uses $DATABASE_URL if set, else the local Docker Compose TimescaleDB on port 5433.
#   sh scripts/load_flow.sh
cd "$(dirname "$0")/.." || exit 1
DATABASE_URL="${DATABASE_URL:-postgresql://smellcast:smellcast@localhost:5433/smellcast}" \
  exec .venv/bin/python -m collectors.usibwc_flow
