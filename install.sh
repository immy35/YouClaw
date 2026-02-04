#!/bin/bash
# YouClaw Installation Script
# Installs YouClaw AI Assistant on your VPS

set -e  # Exit on error

echo "🦞 YouClaw Installation Script"
echo "================================"
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $PYTHON_VERSION found, but Python $REQUIRED_VERSION or higher is required."
    exit 1
fi

echo "✅ Python $PYTHON_VERSION found"

# Check if Ollama is installed
echo ""
echo "Checking for Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found. Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "✅ Ollama installed"
else
    echo "✅ Ollama is already installed"
fi

# Start Ollama service if not running
echo ""
echo "Starting Ollama service..."
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    sudo systemctl start ollama || echo "Note: Ollama service may need manual start"
fi

# Check for available models
echo ""
echo "Checking for Ollama models..."
MODELS=$(ollama list 2>/dev/null | tail -n +2 | wc -l)

if [ "$MODELS" -eq 0 ]; then
    echo "⚠️  No models found. Pulling default model (qwen2.5:1.5b-instruct)..."
    ollama pull qwen2.5:1.5b-instruct
    echo "✅ Model downloaded"
else
    echo "✅ Found $MODELS model(s) already installed"
    ollama list
fi

# Create virtual environment
echo ""
echo "Creating Python virtual environment..."
python3 -m venv venv
echo "✅ Virtual environment created"

# Activate virtual environment and install dependencies
echo ""
echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Create data directory
echo ""
echo "Creating data directory..."
mkdir -p data
echo "✅ Data directory created"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  IMPORTANT: Edit .env file and add your Discord and Telegram bot tokens!"
    echo "   Run: nano .env"
else
    echo ""
    echo "✅ .env file already exists"
fi

# Create systemd service file
echo ""
echo "Creating systemd service file..."
SERVICE_FILE="$HOME/.config/systemd/user/youclaw.service"
mkdir -p "$HOME/.config/systemd/user"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=YouClaw AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python $(pwd)/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo "✅ Systemd service file created"

# Reload systemd
echo ""
echo "Reloading systemd..."
systemctl --user daemon-reload
echo "✅ Systemd reloaded"

# Make youclaw command executable
echo ""
echo "Setting up youclaw CLI command..."
chmod +x youclaw
chmod +x cli.py

# Create symlink for easy access (optional)
YOUCLAW_BIN="$HOME/.local/bin/youclaw"
mkdir -p "$HOME/.local/bin"
ln -sf "$(pwd)/youclaw" "$YOUCLAW_BIN"
echo "✅ youclaw command installed to $YOUCLAW_BIN"

echo ""
echo "================================"
echo "🎉 YouClaw Installation Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your bot tokens:"
echo "   nano .env"
echo ""
echo "2. Run health check:"
echo "   ./youclaw check"
echo ""
echo "3. Start YouClaw:"
echo "   ./youclaw start"
echo "   # or: systemctl --user start youclaw"
echo ""
echo "4. Enable auto-start on boot:"
echo "   systemctl --user enable youclaw"
echo ""
echo "5. View logs:"
echo "   ./youclaw logs -f"
echo ""
echo "6. Open web dashboard:"
echo "   ./youclaw dashboard"
echo "   # Then visit: http://:8080"
echo ""
echo "Available commands:"
echo "  ./youclaw install   # Run installation"
echo "  ./youclaw check     # Health check"
echo "  ./youclaw status    # Service status"
echo "  ./youclaw start     # Start service"
echo "  ./youclaw stop      # Stop service"
echo "  ./youclaw restart   # Restart service"
echo "  ./youclaw logs      # View logs"
echo "  ./youclaw dashboard # Web dashboard"
echo ""
echo "For help, see README.md"
echo ""
