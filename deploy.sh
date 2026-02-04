#!/bin/bash
# Quick deployment script to transfer YouClaw to VPS

VPS_IP="213.32.17.19"
VPS_USER="ubuntu"
LOCAL_DIR="/home/imran/Music/Ai project/youclaw"
REMOTE_DIR="~/youclaw"

echo "🦞 YouClaw Deployment to VPS"
echo "=============================="
echo ""
echo "VPS: $VPS_USER@$VPS_IP"
echo "Local: $LOCAL_DIR"
echo "Remote: $REMOTE_DIR"
echo ""

# Check if we can connect
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 $VPS_USER@$VPS_IP "echo 'Connection successful'" 2>/dev/null; then
    echo "❌ Cannot connect to VPS. Please check:"
    echo "   - VPS IP: $VPS_IP"
    echo "   - SSH access"
    echo "   - Network connection"
    exit 1
fi
echo "✅ SSH connection successful"
echo ""

# Transfer files
echo "Transferring files to VPS..."
rsync -avz --progress \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'data/' \
    --exclude '*.log' \
    "$LOCAL_DIR/" "$VPS_USER@$VPS_IP:$REMOTE_DIR/"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Files transferred successfully!"
    echo ""
    echo "Next steps:"
    echo "1. SSH to VPS:"
    echo "   ssh $VPS_USER@$VPS_IP"
    echo ""
    echo "2. Navigate to project:"
    echo "   cd $REMOTE_DIR"
    echo ""
    echo "3. Configure tokens:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    echo ""
    echo "4. Run installation:"
    echo "   chmod +x install.sh"
    echo "   ./install.sh"
    echo ""
    echo "5. Start YouClaw:"
    echo "   ./youclaw start"
    echo ""
else
    echo "❌ Transfer failed!"
    exit 1
fi
