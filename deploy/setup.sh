#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Oracle Cloud Ubuntu 22.04 — AI Tracker Setup Script
# Run this once on a fresh VM:  bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

REPO="https://github.com/Masterdragon/ai-tracker.git"
APP_DIR="/home/ubuntu/ai-tracker"
SERVICE_NAME="ai-tracker"

echo ""
echo "════════════════════════════════════════"
echo "  AI Tracker — Server Setup"
echo "════════════════════════════════════════"

# ── 1. System update ──────────────────────────────────────────────────────────
echo ""
echo "▶ [1/7] Updating system packages..."
sudo apt update -y && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx ufw curl

# ── 2. Clone repo ─────────────────────────────────────────────────────────────
echo ""
echo "▶ [2/7] Cloning repository..."
if [ -d "$APP_DIR" ]; then
  echo "  Directory exists — pulling latest..."
  cd "$APP_DIR" && git pull
else
  git clone "$REPO" "$APP_DIR"
  cd "$APP_DIR"
fi

# ── 3. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "▶ [3/7] Setting up Python virtual environment..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# ── 4. Create data directory ──────────────────────────────────────────────────
echo ""
echo "▶ [4/7] Creating data directory..."
mkdir -p "$APP_DIR/data"
sudo chown -R ubuntu:ubuntu "$APP_DIR"

# ── 5. Systemd service ────────────────────────────────────────────────────────
echo ""
echo "▶ [5/7] Installing systemd service..."
sudo cp "$APP_DIR/deploy/ai-tracker.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
echo "  Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l

# ── 6. Nginx reverse proxy ────────────────────────────────────────────────────
echo ""
echo "▶ [6/7] Configuring Nginx..."
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/"$SERVICE_NAME"
sudo ln -sf /etc/nginx/sites-available/"$SERVICE_NAME" /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# ── 7. Firewall ───────────────────────────────────────────────────────────────
echo ""
echo "▶ [7/7] Configuring firewall (ufw)..."
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

# ── Done ──────────────────────────────────────────────────────────────────────
PUBLIC_IP=$(curl -s ifconfig.me || echo "<your-public-ip>")
echo ""
echo "════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  Your app is live at:"
echo "  → http://$PUBLIC_IP"
echo ""
echo "  Useful commands:"
echo "  sudo systemctl status ai-tracker   # check app status"
echo "  sudo journalctl -u ai-tracker -f   # view live logs"
echo "  sudo systemctl restart ai-tracker  # restart app"
echo "════════════════════════════════════════"
