#!/usr/bin/env bash
set -euo pipefail

# Generate all required secrets for a fresh AiMANAC deployment.
# Usage: ./generate-env.sh > .env
#   or:  ./generate-env.sh        (writes .env in current directory)

OUT="${1:-.env}"

if [ -f "$OUT" ] && [ "$OUT" = ".env" ]; then
    echo "ERROR: .env already exists. Remove it first or specify a different output file." >&2
    exit 1
fi

ENCRYPTION_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 64)
JWT_REFRESH_SECRET=$(openssl rand -hex 64)
POSTGRES_PASSWORD=$(openssl rand -hex 16)

cat > "$OUT" <<EOF
ENCRYPTION_KEY=${ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}
JWT_REFRESH_SECRET=${JWT_REFRESH_SECRET}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
EOF

echo "Generated $OUT with fresh secrets." >&2
echo "Next: docker compose up -d" >&2
