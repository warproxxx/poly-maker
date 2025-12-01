#!/usr/bin/env bash
set -Eeuo pipefail

# Idempotent bootstrap for Ubuntu 25.04 LTS hosts.
# Creates the deployment user, installs Python and build deps, clones the repo,
# installs uv-managed dependencies, and (optionally) provisions a systemd service.

PROJECT_USER=${PROJECT_USER:-polymaker}
PROJECT_GROUP=${PROJECT_GROUP:-$PROJECT_USER}
PROJECT_HOME=${PROJECT_HOME:-}
PROJECT_DIR=${PROJECT_DIR:-}
REPO_URL=${REPO_URL:-https://github.com/yourusername/polymaker-plus.git}
PYTHON_VERSION=${PYTHON_VERSION:-3.12}
SYSTEMD_SERVICE_NAME=${SYSTEMD_SERVICE_NAME:-polymaker.service}
ENABLE_SERVICE=${ENABLE_SERVICE:-1}

log() {
  printf "[bootstrap] %s\n" "$*"
}

ensure_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (use sudo)." >&2
    exit 1
  fi
}

ensure_user() {
  if ! id -u "$PROJECT_USER" >/dev/null 2>&1; then
    log "Creating user '$PROJECT_USER'"
    adduser --disabled-password --gecos "Polymaker" "$PROJECT_USER"
  fi

  if ! id -nG "$PROJECT_USER" | grep -q "\<sudo\>"; then
    log "Adding '$PROJECT_USER' to sudo group"
    usermod -aG sudo "$PROJECT_USER"
  fi
}

resolve_paths() {
  PROJECT_HOME=${PROJECT_HOME:-$(getent passwd "$PROJECT_USER" | cut -d: -f6)}
  PROJECT_DIR=${PROJECT_DIR:-$PROJECT_HOME/polymaker-plus}
}

install_packages() {
  log "Installing system dependencies"
  apt-get update
  apt-get install -y "python${PYTHON_VERSION}" "python${PYTHON_VERSION}-venv" \
    python3-pip pkg-config libssl-dev libffi-dev git curl
}

install_uv() {
  log "Installing uv for $PROJECT_USER if missing"
  sudo -u "$PROJECT_USER" bash -lc 'command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh'
}

fetch_repo() {
  log "Preparing project directory at $PROJECT_DIR"
  install -d -o "$PROJECT_USER" -g "$PROJECT_GROUP" "$PROJECT_DIR"

  if [[ ! -d "$PROJECT_DIR/.git" ]]; then
    log "Cloning repository from $REPO_URL"
    sudo -u "$PROJECT_USER" git clone "$REPO_URL" "$PROJECT_DIR"
  else
    log "Repository exists; fetching updates"
    sudo -u "$PROJECT_USER" git -C "$PROJECT_DIR" fetch --all --prune
  fi
}

install_dependencies() {
  log "Syncing Python dependencies with uv"
  sudo -u "$PROJECT_USER" bash -lc "cd '$PROJECT_DIR' && export PATH=\"\$HOME/.local/bin:\$PATH\" && uv sync --locked"
}

ensure_env_file() {
  if [[ -f "$PROJECT_DIR/.env" ]]; then
    log ".env already present; not overwriting"
    return
  fi

  if [[ -f "$PROJECT_DIR/.env.example" ]]; then
    log "Copying .env.example to .env (fill in secrets manually)"
    sudo -u "$PROJECT_USER" cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  else
    log "No .env.example found; please create $PROJECT_DIR/.env with required secrets" >&2
  fi
}

write_systemd_unit() {
  local unit_path="/etc/systemd/system/$SYSTEMD_SERVICE_NAME"

  log "Writing systemd service to $unit_path"
  cat > "$unit_path" <<EOF2
[Unit]
Description=Polymaker Plus market maker
After=network-online.target
Wants=network-online.target

[Service]
User=$PROJECT_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
Environment=PATH=$PROJECT_HOME/.local/bin:/usr/local/bin:/usr/bin
ExecStart=$PROJECT_HOME/.local/bin/uv run python main.py
Restart=on-failure
RestartSec=5

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOF2

  systemctl daemon-reload
  systemctl enable --now "$SYSTEMD_SERVICE_NAME"
}

main() {
  ensure_root
  ensure_user
  resolve_paths
  install_packages
  install_uv
  fetch_repo
  install_dependencies
  ensure_env_file

  if [[ "$ENABLE_SERVICE" -eq 1 ]]; then
    write_systemd_unit
  else
    log "Skipping systemd service creation (ENABLE_SERVICE=$ENABLE_SERVICE)"
  fi

  log "Bootstrap complete. If you copied .env from example, fill in secrets before starting."
}

main "$@"
