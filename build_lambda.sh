#!/usr/bin/env bash
# Build the Lambda bundle: locked runtime dependencies as manylinux_2_28 aarch64 wheels
# (Graviton; Lambda python3.14 runs on Amazon Linux 2023, glibc 2.34)
# plus the overclouded package. No dev dependencies, no secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/.lambda-build"
OUT="$BUILD/bundle"
rm -rf "$OUT"
mkdir -p "$OUT"
cd "$ROOT/backend"
uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt \
  -o "$BUILD/requirements.txt" >/dev/null
uv pip install \
  --requirement "$BUILD/requirements.txt" \
  --target "$OUT" \
  --python-platform aarch64-manylinux_2_28 \
  --python-version 3.14 \
  --no-build \
  --quiet
cp -r src/overclouded "$OUT/"
cp "$ROOT/infra/customer-role/overclouded-readonly-role.yaml" "$OUT/overclouded/customer_role.yaml"
find "$OUT" -type d -name "__pycache__" -prune -exec rm -rf {} +
# boto3/botocore ship in the Lambda runtime too, but we pin our own (verified models, D-05).
du -sh "$OUT" | awk '{print "Lambda bundle: " $1}'
