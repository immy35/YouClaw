# YouClaw Docker Onboarding Guide 🐳🦞

Docker is the most stable and professional way to run YouClaw. It packages everything into a single container so you don't have to worry about Python versions, `pip` errors, or environment issues.

## 1. Prerequisites
- [Docker Installed](https://docs.docker.com/get-docker/)
- [Docker Compose Installed](https://docs.docker.com/compose/install/)

## 2. One-Command Setup
Go to your project folder and run:
```bash
docker-compose up -d
```

## 3. Onboarding Flow
Once the container is running:
1.  **Open Dashboard**: Go to `http://localhost:8080` in your browser.
2.  **Configuration**: 
    - The dashboard will detect if you are unconfigured.
    - You can paste your **Ollama URL**, **Telegram Token**, and **Discord Token** directly in the **Root Protocols** panel.
    - Click **"Connect Core 🔌"** to save instantly.

## 4. Maintenance
- **Stop**: `docker-compose stop`
- **Restart**: `docker-compose restart`
- **Logs**: `docker-compose logs -f`

## 5. Persistence
All your chat history and settings are saved in the `./data` folder on your computer. Even if you "delete" the container, your data stays safe! 🛡️
