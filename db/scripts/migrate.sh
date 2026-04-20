#!/usr/bin/env bash
# Apply all SQL migrations in order.
# Usage: pnpm db:migrate
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"

MIGRATIONS_DIR="$(dirname "$0")/../migrations"

echo "Applying migrations from $MIGRATIONS_DIR"

for f in "$MIGRATIONS_DIR"/*.sql; do
  echo "  -> $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "Migrations complete."
