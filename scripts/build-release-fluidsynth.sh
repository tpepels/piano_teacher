#!/usr/bin/env bash
# Build the Linux release SF2 renderer; use the shipped source for offline rebuilds.
set -Eeuo pipefail
stage=$(realpath -m "${1:?pass the package staging directory}")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
sources="$stage/licenses/FluidSynth"
mkdir -p "$stage/runtime/lib" "$sources" "$work/source"
version=2.6.3
gcem=012ae73c6d0a2cb09ffe86475f5c6fba3926e200
if [[ -n ${PIANO_FLUIDSYNTH_SOURCE:-} ]]; then
  tar -xzf "$PIANO_FLUIDSYNTH_SOURCE" -C "$work/source"
else
  curl --fail --location --silent --show-error --retry 3 --max-time 120 \
    "https://codeload.github.com/FluidSynth/fluidsynth/tar.gz/refs/tags/v$version" -o "$work/fluid.tar.gz"
  curl --fail --location --silent --show-error --retry 3 --max-time 120 \
    "https://codeload.github.com/kthohr/gcem/zip/$gcem" -o "$work/gcem.zip"
  (cd "$work" && sha256sum -c <<EOF
c51ebe04c8a445f4a7dd5a86e09a27b5c5af547756574edc52fc61c88ebe8427  fluid.tar.gz
28159274c54e9640354852e172d10d88eb159f4e7f2fea42edbcd20105ed3526  gcem.zip
EOF
  )
  # Upstream test instruments are independent works unused by the library target.
  tar --exclude="fluidsynth-$version/sf2" -xzf "$work/fluid.tar.gz" --strip-components=1 -C "$work/source"
  (cd "$work" && cmake -E tar xf gcem.zip)
  cp -r "$work/gcem-$gcem/include" "$work/gcem-$gcem/LICENSE" "$work/source/gcem/"
fi
disabled=()
for feature in alsa aufile dbus jack ladspa libsndfile midishare network oss portaudio \
    pulseaudio pipewire readline sdl3 systemd openmp native-dls signalsmith; do
  disabled+=("-Denable-$feature=OFF")
done
cmake -S "$work/source" -B "$work/build" -DCMAKE_BUILD_TYPE=Release \
  -DGCEM_INCLUDE_DIR="$work/source/gcem/include" "${disabled[@]}"
cmake --build "$work/build" --target libfluidsynth --parallel 4
install -m 755 "$work/build/src/libfluidsynth.so.3" "$stage/runtime/lib/libfluidsynth.so.3"
install -m 644 "$work/source/LICENSE" "$sources/LICENSE"
install -m 644 "$work/source/gcem/LICENSE" "$sources/GCEM-LICENSE"
install -m 644 "$0" "$sources/build-release-fluidsynth.sh"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -czf "$sources/fluidsynth-$version-source.tar.gz" -C "$work/source" .
