# Build against Debian 12 instead of inheriting the developer machine ABI.
FROM python:3.14.10-slim-bookworm@sha256:e60ad028afdcdd14772a3d46decf0eaf616720f9102aeb4397a2045ff6718c3d AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake curl git pkg-config unzip libasound2-dev libjack-jackd2-dev \
    libcairo2 libfontconfig1 libgl1 libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY pyproject.toml .
RUN python -c 'import subprocess,sys,tomllib; p=tomllib.load(open("pyproject.toml","rb"))["project"]; subprocess.check_call([sys.executable,"-m","pip","install","--no-cache-dir","scons",*p["dependencies"],*p["optional-dependencies"]["godot"]])'
RUN curl -fsSL --retry 3 --max-time 180 https://github.com/godotengine/godot-builds/releases/download/4.7.2-stable/Godot_v4.7.2-stable_linux.x86_64.zip -o /tmp/godot.zip \
    && echo "9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65  /tmp/godot.zip" | sha512sum -c - \
    && unzip -p /tmp/godot.zip Godot_v4.7.2-stable_linux.x86_64 > /usr/local/bin/godot \
    && chmod +x /usr/local/bin/godot && rm /tmp/godot.zip
COPY native native
COPY scripts/build-inprocess.sh scripts/dev_runtime_state.py scripts/
ENV PIANO_PYTHON=/usr/local/bin/python3 PIANO_SKIP_NATIVE_SMOKE=1
RUN PIANO_GODOT_CPP_PROFILE=/workspace/native/release-profile.json bash scripts/build-inprocess.sh
COPY . .
ENV PIANO_BUNDLED_PYTHON_HOME=/usr/local PIANO_GODOT_BINARY=/usr/local/bin/godot
RUN bash scripts/package-inprocess.sh && mkdir /release && cp dist/*.tar* dist/runtime-inventory.json /release/

FROM scratch AS artifacts
COPY --from=builder /release/ /
