# ── Stage 1: Frontend Build ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build

# Enable pnpm via corepack
RUN corepack enable && corepack prepare pnpm@latest --activate

# Install dependencies (cached layer)
COPY frontend-react/package.json frontend-react/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Build
COPY frontend-react/ .
RUN pnpm build

# ── Stage 2: Application ───────────────────────────────────────────────────────
FROM python:3.12-slim AS app

# System dependencies
# - openssh-client: Ansible needs ssh binary to connect to remote hosts
# - git: Terraform provider downloads
# - curl + unzip: Download Terraform binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    git \
    curl \
    unzip \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Install Terraform (pinned to match production)
# SHA-256 verified against HashiCorp's published checksums to prevent
# supply-chain substitution on a compromised CDN or MITM.
ARG TERRAFORM_VERSION=1.14.5
ARG TARGETARCH
RUN set -eux; \
    tf_zip="terraform_${TERRAFORM_VERSION}_linux_${TARGETARCH}.zip"; \
    tf_zip_path="/tmp/${tf_zip}"; \
    curl -fsSL \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/${tf_zip}" \
      -o "${tf_zip_path}"; \
    tf_sha256="$(curl -fsSL \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" \
      | awk -v tf_zip="${tf_zip}" '$2 == tf_zip {print $1}')"; \
    [ -n "${tf_sha256}" ]; \
    echo "${tf_sha256}  ${tf_zip_path}" | sha256sum -c -; \
    unzip "${tf_zip_path}" -d /usr/local/bin/; \
    rm "${tf_zip_path}"; \
    terraform version

# Install Ansible via pip (ansible-core is lighter than full ansible package)
RUN pip install --no-cache-dir "ansible-core>=2.17,<2.18" \
    && ansible-galaxy collection install community.general ansible.posix

WORKDIR /app

# Install Python dependencies (cached layer — copy requirements first)
COPY requirements.txt .
RUN pip install --no-cache-dir "setuptools>=68.0.0,<81.0.0" && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Copy built frontend from stage 1
COPY --from=frontend-build /build/dist/ /app/frontend-react/dist/

# Preserve bundled default preset outside /app/configs so entrypoint can seed
# an empty runtime volume on first boot.
RUN if [ -d /app/configs/presets/default ]; then \
      mkdir -p /app/.image-defaults/presets && \
      cp -a /app/configs/presets/default /app/.image-defaults/presets/default; \
    fi

# Create directories that will be overlaid by named volumes at runtime
RUN mkdir -p \
    /app/data \
    /app/terraform/ssh-keys \
    /app/terraform/vultr-root/terraform.tfstate.d \
    /app/ansible/inventory \
    /app/configs \
    /app/logs

# Make FLASK_APP available in all exec sessions (e.g. docker compose exec web flask ...)
# PYTHONUNBUFFERED prevents print/logging buffering issues in containerised workers
ENV FLASK_APP="ui:create_app()" \
    PYTHONUNBUFFERED=1

# Entrypoint handles: secret generation, DB init, migrations
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

# Default command — overridden per service in docker-compose.yml
CMD ["gunicorn", \
     "--config", "gunicorn.conf.py", \
     "--workers", "1", \
     "--threads", "12", \
     "--bind", "0.0.0.0:5001", \
     "--timeout", "120", \
     "ui:create_app()"]
