# Target-system verification, separate from the release builder.
FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash procps ca-certificates libasound2 libjack-jackd2-0 libcairo2 \
    libfontconfig1 libgl1 libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 \
    libxext6 libxrender1 libxkbcommon0 libpulse0 libudev1 libdbus-1-3 \
    libssl3 libbz2-1.0 libffi8 liblzma5 libsqlite3-0 libreadline8 libncursesw6 \
    libgdbm6 libgdbm-compat4 libexpat1 libuuid1 zlib1g libcrypt1 \
    libstdc++6 libgcc-s1 libgomp1 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp
