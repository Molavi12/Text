#!/bin/bash
# ============================================================================
# deploy.sh — Soroush+ Live Stream — One-Command Auto Deploy
# ============================================================================
# This script connects to your segfault.net VPS and runs the full setup.
# It uses the SSH key saved in ~/.ssh/id_sf-adm-segfault-net
#
# Usage:
#   bash deploy.sh              # Deploy with defaults
#   bash deploy.sh --redeploy   # Kill existing and redeploy
#
# The VPS must already be created (you have a SECRET saved).
# ============================================================================
set -euo pipefail

# ===== Configuration =====
VPS_SECRET_FILE="/home/z/my-project/splus/vps_secret.txt"
SSH_KEY="/home/z/.ssh/id_sf-adm-segfault-net"
SSH_CONFIG_HOST="splus-vps"
VPS1_DIRECT_URL="https://tmpfiles.org/dl/1785598546.7dee930e2dbc4030/wOwBR80nrK0O/vps1.sh"

HLS_URL="${HLS_URL:-https://dev-live.livetvstream.co.uk/LS-63503-4/index.m3u8}"
GROUP_ID="${GROUP_ID:--10023299695}"
CALL_TITLE="${CALL_TITLE:-لایو ۲۴ ساعته}"

# ===== Colors =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

msg()  { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }

# ===== Step 1: Check prerequisites =====
msg "============================================"
msg "  Soroush+ Live — Auto Deploy"
msg "============================================"
echo ""

msg "[1/5] Checking prerequisites..."

# Check SSH key
if [ ! -f "${SSH_KEY}" ]; then
    err "SSH key not found: ${SSH_KEY}"
    err "You need to create a VPS first and save the SSH key."
    err "Run: ssh root@segfault.net (password: segfault)"
    err "Then save the key and SECRET from the VPS."
    exit 1
fi
info "  SSH key: ${SSH_KEY} ✓"

# Check VPS SECRET
if [ ! -f "${VPS_SECRET_FILE}" ]; then
    err "VPS SECRET not found: ${VPS_SECRET_FILE}"
    err "You need to create a VPS first and save the SECRET."
    exit 1
fi
SECRET=$(cat "${VPS_SECRET_FILE}")
info "  SECRET: ${SECRET:0:4}**** ✓"

# Check SSH config
if grep -q "Host ${SSH_CONFIG_HOST}" /home/z/.ssh/config 2>/dev/null; then
    info "  SSH config: ${SSH_CONFIG_HOST} ✓"
else
    warn "  SSH config for '${SSH_CONFIG_HOST}' not found in ~/.ssh/config"
    warn "  Will use direct SSH command instead"
fi

echo ""

# ===== Step 2: Determine SSH connection method =====
msg "[2/5] Connecting to VPS..."

# Try SSH config first, then direct
SSH_CMD=""
if grep -q "Host ${SSH_CONFIG_HOST}" /home/z/.ssh/config 2>/dev/null; then
    SSH_CMD="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=no ${SSH_CONFIG_HOST}"
else
    # Direct SSH with key and SECRET
    SSH_CMD="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=no -i ${SSH_KEY} root@segfault.net"
fi

# Test connection
info "  Testing SSH connection..."
if ${SSH_CMD} "echo CONNECTION_OK" 2>/dev/null | grep -q "CONNECTION_OK"; then
    info "  VPS connection: OK ✓"
else
    warn "  SSH config/key connection failed, trying with password..."
    # Try with sshpass + segfault password
    if command -v sshpass &>/dev/null; then
        SSH_CMD="sshpass -p segfault ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=no root@segfault.net"
        if ${SSH_CMD} "echo CONNECTION_OK" 2>/dev/null | grep -q "CONNECTION_OK"; then
            info "  VPS connection via password: OK ✓"
        else
            err "  Cannot connect to VPS!"
            exit 1
        fi
    else
        err "  Cannot connect to VPS! Check your SSH key and SECRET."
        err "  You may need to reconnect to segfault.net first."
        exit 1
    fi
fi

echo ""

# ===== Step 3: Handle redeploy flag =====
if [ "${1:-}" = "--redeploy" ]; then
    msg "[3/5] Killing existing processes (redeploy)..."
    ${SSH_CMD} "screen -S splus_live -X quit 2>/dev/null; screen -S keepalive -X quit 2>/dev/null; pkill -f splus_live.py 2>/dev/null; pkill -f keepalive.sh 2>/dev/null; echo Done" 2>/dev/null || true
else
    msg "[3/5] Checking for existing deployment..."
    EXISTING=$(${SSH_CMD} "screen -list 2>/dev/null | grep -c splus_live" 2>/dev/null || echo "0")
    if [ "${EXISTING}" -gt 0 ]; then
        warn "  Existing splus_live session found! Use --redeploy to replace it."
        warn "  Skipping deployment. Current status:"
        ${SSH_CMD} "screen -list" 2>/dev/null
        echo ""
        msg "To redeploy: bash deploy.sh --redeploy"
        exit 0
    fi
    info "  No existing deployment found, proceeding..."
fi

echo ""

# ===== Step 4: Download and run vps1.sh on VPS =====
msg "[4/5] Deploying vps1.sh on VPS..."
info "  Download URL: ${VPS1_DIRECT_URL}"

# Execute the deployment on VPS
# We download vps1.sh and run it in a screen session so it persists
${SSH_CMD} bash -c "
    set -e
    echo '  Downloading vps1.sh...'
    curl -fsSL --connect-timeout 15 --max-time 60 -o /tmp/vps1.sh '${VPS1_DIRECT_URL}'
    chmod +x /tmp/vps1.sh
    echo '  Starting vps1.sh in screen session...'
    export HLS_URL='${HLS_URL}'
    export GROUP_ID='${GROUP_ID}'
    export CALL_TITLE='${CALL_TITLE}'
    screen -dmS deploy bash /tmp/vps1.sh
    sleep 3
    echo '  Deployment started!'
    screen -list
"

echo ""

# ===== Step 5: Verify deployment =====
msg "[5/5] Verifying deployment..."
sleep 5

DEPLOY_STATUS=$(${SSH_CMD} "screen -list 2>/dev/null" 2>/dev/null || echo "Unable to check")
echo "${DEPLOY_STATUS}"

echo ""
msg "============================================"
msg "  DEPLOYMENT INITIATED!"
msg "============================================"
echo ""
msg "  The vps1.sh script is running inside the VPS."
msg "  It will:"
msg "    1. Download browser_state.json & inject.js"
msg "    2. Install system dependencies (apt, pip)"
msg "    3. Install Playwright + Chromium"
msg "    4. Create splus_live.py & keepalive.sh"
msg "    5. Start the live stream"
echo ""
msg "  This takes about 3-5 minutes."
echo ""
msg "  To monitor progress:"
msg "    ${SSH_CMD} 'tail -f /sec/splus/live.log'"
echo ""
msg "  To attach to the live stream:"
msg "    ${SSH_CMD} 'screen -r splus_live'"
echo ""
msg "  To check status:"
msg "    ${SSH_CMD} 'screen -list'"
echo ""
msg "  HLS: ${HLS_URL}"
msg "  Group: ${GROUP_ID}"
msg "============================================"
