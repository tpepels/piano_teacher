#!/usr/bin/env bash
# Collect exact source inputs for the separately downloadable Linux library sources.
set -Eeuo pipefail
release=$1
output=$2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
site=("$release"/runtime/python/lib/python*/site-packages)

fetch() {
  local filename=$1 url=$2 digest=$3
  if [[ -f "${PIANO_RELEASE_SOURCE_CACHE:-/nonexistent}/$filename" ]]; then
    cp "$PIANO_RELEASE_SOURCE_CACHE/$filename" "$work/$filename"
  else
    curl -fsSL --retry 3 --max-time 120 "$url" -o "$work/$filename"
  fi
  echo "$digest  $work/$filename" | sha256sum --check --status
}

# The ELF build IDs survived auditwheel SONAME/RPATH repair. Compare both to
# their original AlmaLinux RPMs before associating the common GCC source RPM.
for pair in libgfortran:04dbe32dceb80654422140fb7641f732065999c8 libquadmath:c1c5f8d61f17e5579c4e85718845b74e4b94116c; do
  libraries=("${site[0]}"/numpy.libs/"${pair%:*}"*.so*)
  if [[ ${#libraries[@]} != 1 || ! -f "${libraries[0]}" ]]; then
    echo "Expected NumPy's separate ${pair%:*} library for the recorded GCC sources." >&2
    echo "Use the verified Linux release constraints or review the installed wheel's native libraries." >&2
    exit 1
  fi
  build_id=$(readelf -n "${libraries[0]}" | sed -n 's/.*Build ID: //p')
  if [[ $build_id != "${pair#*:}" ]]; then
    echo "Review matching source RPM for ${libraries[0]} ($build_id)" >&2
    exit 1
  fi
done
gcc='gcc-8.5.0-28.el8_10.alma.1.src.rpm'
fetch "$gcc" "https://vault.almalinux.org/8/BaseOS/Source/Packages/$gcc" \
  c94dbbd2cd6d5d01a5a6822ea18f8ce34942c25a80e17b4682d547d5e652dbd0

if [[ ! -d "${site[0]}/verovio-5.7.0.dist-info" ]]; then
  echo "Review the Verovio source archive and font notices for this wheel version." >&2
  exit 1
fi
verovio='verovio-5.7.0.tar.gz'
fetch "$verovio" "https://files.pythonhosted.org/packages/1c/ce/975d7295c436dc24ae8a77910053a6b8831060282e3be41adef5c6fc5f6a/$verovio" \
  f51cbaf49574a85a8d2d136a0f1feded641322f6f4d639cfe0087216979f68f3
tar -C "$work" --exclude=verovio-5.7.0/data/Liberation.css -xzf "$work/$verovio"
tar -C "$work" -czf "$work/verovio-runtime-source.tar.gz" verovio-5.7.0
tar -cf "$output" -C "$work" "$gcc" verovio-runtime-source.tar.gz \
  -C "$release/licenses" Library-sources.txt Verovio-fonts.txt
