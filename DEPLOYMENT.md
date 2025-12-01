# Deployment Guide (Ubuntu 25.04 LTS)

This guide describes a hardened, reproducible way to deploy Polymaker Plus on Ubuntu 25.04 LTS. It assumes a fresh server with sudo access.

## 1) Prepare the host (manual)
- Install OS dependencies and a recent Python toolchain:
  ```bash
  sudo apt update
  sudo apt install -y python3.12 python3.12-venv python3-pip pkg-config libssl-dev libffi-dev git curl
  ```
- Create a dedicated, non-root user to limit blast radius:
  ```bash
  sudo adduser --disabled-password --gecos "Polymaker" polymaker
  sudo usermod -aG sudo polymaker
  ```
- Enable a basic firewall (allow SSH only, or add HTTPS if needed for dashboards):
  ```bash
  sudo ufw allow OpenSSH
  sudo ufw enable
  ```

## 1b) Prepare the host automatically (recommended)
To automate host provisioning and stay close to these steps, run the bootstrap script as root:

```bash
sudo ./scripts/bootstrap_ubuntu.sh
```

The script will:
- Install Python 3.12, build essentials, git, curl, and `uv` for dependency management.
- Create (or reuse) the `polymaker` user, add it to `sudo`, and clone this repo into `/home/polymaker/polymaker-plus`.
- Copy `.env.example` to `.env` if missing (fill in your secrets afterward).
- Optionally provision and start the `polymaker.service` systemd unit (set `ENABLE_SERVICE=0` to skip).

You can customize defaults with environment variables, e.g. `PROJECT_USER`, `PROJECT_DIR`, `REPO_URL`, `SYSTEMD_SERVICE_NAME`, or `ENABLE_SERVICE=0`.

## 2) Fetch the code and install dependencies
- Switch to the deployment user and clone the repo:
  ```bash
  sudo -iu polymaker
  git clone https://github.com/yourusername/polymaker-plus.git
  cd polymaker-plus
  ```
- Install [uv](https://github.com/astral-sh/uv) for deterministic Python environments:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  ```
- Create an isolated environment and install dependencies:
  ```bash
  uv sync --locked
  # include dev extras only if you run tests/formatters on the server
  # uv sync --locked --extra dev
  ```

## 3) Configure credentials and data inputs
- Copy the sample environment and fill in secrets:
  ```bash
  cp .env.example .env
  ```
- Edit `.env` with your Polymarket private key (`PK`), wallet address (`BROWSER_ADDRESS`), and the Google Sheets URL (`SPREADSHEET_URL`).
- Place Google service account JSON credentials alongside the code, and grant the service account edit access to the sheet.
- (Optional) Use a secrets manager (e.g., `pass`, `sops`, or cloud KMS) and template the `.env` file during deployment to avoid storing secrets on disk.

## 4) Create a systemd service
Running the bot as a service keeps it alive across reboots and restarts it on failure.

Create `/etc/systemd/system/polymaker.service` as root:
```ini
[Unit]
Description=Polymaker Plus market maker
After=network-online.target
Wants=network-online.target

[Service]
User=polymaker
WorkingDirectory=/home/polymaker/polymaker-plus
EnvironmentFile=/home/polymaker/polymaker-plus/.env
# Ensure uv is on PATH
Environment=PATH=/home/polymaker/.local/bin:/usr/local/bin:/usr/bin
ExecStart=/home/polymaker/.local/bin/uv run python main.py
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=/home/polymaker/polymaker-plus

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now polymaker.service
systemctl status polymaker.service
```

## 5) Monitoring and logging
- View logs with `journalctl -u polymaker -f`.
- Consider log rotation using `journald` defaults or ship logs to a central sink (e.g., Loki, CloudWatch).
- Add a lightweight health check (e.g., a cron job that alerts if `systemctl is-active polymaker` is non-zero).

## 6) Updating
- Pull changes and re-sync dependencies:
  ```bash
  cd /home/polymaker/polymaker-plus
  git pull
  uv sync --locked
  sudo systemctl restart polymaker.service
  ```

## 7) Optional hardening
- Use `iptables`/`ufw` egress rules to limit traffic to required Polymarket/GSheets endpoints.
- Keep the host patched (`sudo unattended-upgrades` or a weekly patch cycle).
- Run the bot behind a VPN or bastion if exposing management endpoints.
- Snapshot the server or keep IaC (Terraform/Ansible) scripts to recreate it quickly.

## Quick smoke test
After deployment, verify connectivity and data ingestion:
```bash
sudo -iu polymaker
cd ~/polymaker-plus
uv run python update_markets.py --help
uv run python main.py --help  # stop after confirming it starts
```
