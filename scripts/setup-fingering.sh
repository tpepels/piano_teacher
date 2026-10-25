#!/usr/bin/env bash
# Install once; inference never accesses the network or downloads weights.
set -Eeuo pipefail
cd "$(dirname "$0")/../piano_teacher/fingering/lumikey_runtime"
command -v node >/dev/null
command -v npm >/dev/null
# CPU binaries are included in the pinned package. Skip optional CUDA download.
export ONNXRUNTIME_NODE_INSTALL=skip
npm ci --omit=dev
node bridge.cjs <<'JSON'
{"notes":[{"source_id":"setup-check-left","left":true,"note":48,"time":0,"duration":500},{"source_id":"setup-check-right","left":false,"note":60,"time":0,"duration":500}]}
JSON
echo
echo 'Local CPU fingering runtime ready (both pretrained models verified).'
