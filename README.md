# 🦞 YouClaw - Your Personal AI Assistant

**YouClaw** is a powerful, self-hosted AI assistant that connects to Telegram, Discord, and a beautiful web dashboard. Built with privacy in mind, all your data stays on your machine.

## ✨ Features

- 🤖 **Multi-Platform**: Telegram, Discord, and Web Dashboard
- 🧠 **Semantic Memory**: Remembers context using vector embeddings
- ⚡ **AI Cron Jobs**: Schedule recurring AI-powered tasks
- 🔍 **Real-Time Search**: Integrated web search for up-to-date information
- 📧 **Email Integration**: Send and check emails via AI commands
- 🎭 **Multiple Personalities**: Switch between different AI personas
- 🛡️ **Admin Controls**: Full control over your personal instance
- 📦 **Self-Contained**: No external API keys required (uses local Ollama)

## 🚀 Quick Start (Source Installation)

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/immy35/YouClaw.git
   cd YouClaw
   ```

2. **Install local dependencies:**
   ```bash
   python3 -m pip install -e . --user
   ```

3. **Configure Environment:**
   YouClaw uses a `.env` file for configuration. It will be created automatically in `~/.youclaw/.env` on first run, but you can also set variables manually.

### Running YouClaw

Run the bot directly from the source code:

```bash
PYTHONPATH=src python3 -m youclaw.bot
```

**For background execution (VPS/Server):**
```bash
PYTHONPATH=src nohup python3 -m youclaw.bot > youclaw.log 2>&1 &
```

### Access Dashboard

After starting the bot, access your Mission Control at:
```
http://localhost:8080
```
*(Or your VPS IP address:8080)*

## 📖 Usage

### CLI Commands (Source Mode)

If you installed with `pip install -e .`, you can also use the `youclaw` command directly:

```bash
youclaw start      # Start YouClaw
youclaw check      # Health check
```

### Creating Your First Admin Account

1. Navigate to the dashboard (http://localhost:8080)
2. Click "Register"
3. Create your account (first user is automatically admin)
4. Link your Telegram/Discord account in the dashboard to enable full features.

## 🔧 Configuration

YouClaw stores data in `~/.youclaw/` (Linux/Mac) or `%USERPROFILE%\.youclaw\` (Windows).

### Key Environment Variables (`~/.youclaw/.env`)

```bash
OLLAMA_HOST=http://localhost:11434
TELEGRAM_BOT_TOKEN=your_token_here
DISCORD_BOT_TOKEN=your_token_here
SEARCH_ENGINE_URL=http://your-search-engine/search
```

## 🛡️ Security

- **Universal Admin**: Every user on your personal clone has full admin rights
- **Local-First**: All data stays on your machine
- **Token-Based Auth**: Secure session management for the dashboard
- **No Cloud Dependencies**: Runs entirely offline (except for bot platforms)

## 📝 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions are welcome! This is an open-source personal AI assistant project.
