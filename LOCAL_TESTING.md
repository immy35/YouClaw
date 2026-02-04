# YouClaw Local Testing Guide

## Quick Local Test (Without Installing Ollama)

Since you have Ollama on your VPS, you can test YouClaw locally by connecting to your VPS's Ollama!

### Step 1: Create .env file

```bash
cd "/home/imran/Music/Ai project/mybot"
cp .env.example .env
nano .env
```

### Step 2: Configure to use VPS Ollama

Edit `.env`:

```env
# Use your VPS Ollama (no local installation needed!)
OLLAMA_HOST=http://213.32.17.19:11434
OLLAMA_MODEL=qwen2.5:1.5b-instruct

# Add your bot tokens
DISCORD_BOT_TOKEN=your_actual_discord_token
TELEGRAM_BOT_TOKEN=your_actual_telegram_token

# Optional: Disable platform you don't want to test
ENABLE_DISCORD=true
ENABLE_TELEGRAM=false
```

### Step 3: Open Ollama port on VPS

SSH to your VPS and allow external connections:

```bash
ssh ubuntu@213.32.17.19

# Allow Ollama port
sudo ufw allow 11434

# Configure Ollama to listen on all interfaces
sudo systemctl edit ollama

# Add these lines:
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"

# Save and restart
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

### Step 4: Install Python dependencies locally

```bash
cd "/home/imran/Music/Ai project/mybot"

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 5: Test connection to VPS Ollama

```bash
curl http://213.32.17.19:11434/api/tags
```

Should show your qwen2.5:1.5b-instruct model.

### Step 6: Run YouClaw locally

```bash
source venv/bin/activate
python bot.py
```

### Step 7: Test the bot

**Discord:** Send a DM or mention the bot  
**Telegram:** Send a message

YouClaw will run on your laptop but use the AI model on your VPS!

---

## Alternative: Install Ollama Locally

If you want to install Ollama on your laptop:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a small model for testing
ollama pull qwen2.5:1.5b-instruct

# Then use local Ollama in .env:
OLLAMA_HOST=http://localhost:11434
```

---

## Quick Commands

```bash
# Activate environment
source venv/bin/activate

# Run bot
python bot.py

# Run health check
python cli.py check

# Run dashboard
python dashboard.py
```

---

## Expected Output

When you run `python bot.py`, you should see:

```
🦞 Initializing YouClaw...
Configuration: ...
✅ Ollama connected: http://213.32.17.19:11434 (model: qwen2.5:1.5b-instruct)
✅ Memory manager initialized
🚀 YouClaw initialization complete!
Starting Discord handler...
Starting Telegram handler...
Discord bot logged in as YourBot#1234
Telegram bot started
✅ All platforms started. YouClaw is now online! 🦞
```

Press Ctrl+C to stop.
