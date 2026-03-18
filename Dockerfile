FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    gnupg \
    libcap2 \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# Install puccini (TOSCA library)
RUN wget -q https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb -O /tmp/puccini.deb \
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


ENTRYPOINT ["python", "src/ra.py"]
