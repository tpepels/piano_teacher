#!/usr/bin/env bash
# Export desktop release artifacts for Linux x86-64 into the selected directory.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
destination=$(realpath -m "${1:-dist}")
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
git ls-files -z -- native scripts godot piano_teacher pyproject.toml | \
  tar --null -T - -cf - | tar -C "$context" -xf -
docker buildx build --platform linux/amd64 --file "$context/scripts/release/linux.Dockerfile" \
  --output "type=local,dest=$destination" "$context"
