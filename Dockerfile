FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    gnupg \
    nano \
    libcap2 \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

ARG PUCCINI_AMD64_URL="https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb"
ARG PUCCINI_ARM64_URL="https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_arm64.deb"
ARG PUCCINI_ARMV7_URL="https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_armv7.deb"

# Install puccini (TOSCA library)
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) puccini_url="$PUCCINI_AMD64_URL" ;; \
        arm64) puccini_url="$PUCCINI_ARM64_URL" ;; \
        armhf) puccini_url="$PUCCINI_ARMV7_URL" ;; \
        *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
    esac \
    && if [ -z "$puccini_url" ]; then echo "Missing Puccini download URL for architecture: $arch" >&2; exit 1; fi \
    && wget -q "$puccini_url" -O /tmp/puccini.deb \
    && (dpkg -i /tmp/puccini.deb || apt-get install -f -y) \
    && rm /tmp/puccini.deb

# Install opentofu
RUN curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/install-opentofu.sh \
    && chmod +x /tmp/install-opentofu.sh \
    && /tmp/install-opentofu.sh --install-method deb \
    && rm /tmp/install-opentofu.sh

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY k3s/ ./k3s

# Create directories used at runtime
RUN mkdir -p KB


ENTRYPOINT ["python", "src/ra.py"]
