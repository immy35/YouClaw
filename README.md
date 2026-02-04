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

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally

### Installation

```bash
pip install youclaw
```

### First Run

```bash
youclaw start
```

This will launch the **Neural Wizard** - an interactive setup that guides you through:
- Telegram bot token configuration
- Discord bot token configuration  
- Search engine URL (optional)
- Email credentials (optional)

You can skip any step and configure it later via the dashboard.

### Access Dashboard

After setup, access your Mission Control at:
```
http://localhost:8080
```

## 📖 Usage

### CLI Commands

```bash
youclaw start      # Start YouClaw (runs wizard if unconfigured)
youclaw check      # Health check
youclaw dashboard  # Start dashboard only
```

### Creating Your First Admin Account

1. Navigate to `http://localhost:8080`
2. Click "Register"
3. Create your account (first user is automatically admin)
4. Access the ROOT PROTOCOLS panel at the bottom

## 🔧 Configuration

YouClaw stores configuration in `.env` and uses SQLite for data persistence.

### Environment Variables

```bash
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b-instruct
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

## 🐛 Issues

Report issues on GitHub: [Your Repository URL]

## 💬 Community

Join the discussion: [Your Community Link]

---

**Made with 🦞 by the YouClaw Community**
