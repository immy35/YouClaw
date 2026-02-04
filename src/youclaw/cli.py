"""
YouClaw CLI - Command Line Interface
Provides commands for installation, health checks, and management.
"""

import sys
import subprocess
import os
import signal
import time
import asyncio
import argparse
from pathlib import Path

# Add parent directory to path for imports if running locally
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))


class YouClawCLI:
    """YouClaw command line interface"""
    
    def __init__(self):
        self.project_dir = Path(__file__).parent
    
    def cmd_install(self, args):
        """Run installation script"""
        print("🦞 Running YouClaw installation...")
        install_script = self.project_dir / "install.sh"
        
        if not install_script.exists():
            print("❌ install.sh not found!")
            return 1
        
        result = subprocess.run(["bash", str(install_script)])
        return result.returncode
    
    def cmd_check(self, args):
        """Run health checks"""
        print("🦞 YouClaw Health Check")
        print("=" * 50)
        
        # Check Python version
        print("\n📦 Python Version:")
        python_version = sys.version.split()[0]
        print(f"   {python_version}", end="")
        if sys.version_info >= (3, 10):
            print(" ✅")
        else:
            print(" ❌ (Need 3.10+)")
        
        # Check Ollama
        print("\n🤖 Ollama:")
        try:
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/tags"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print("   Connected ✅")
                # Parse models
                import json
                try:
                    data = json.loads(result.stdout)
                    models = [m["name"] for m in data.get("models", [])]
                    print(f"   Models: {', '.join(models) if models else 'None'}")
                except:
                    pass
            else:
                print("   Not running ❌")
        except Exception as e:
            print(f"   Error: {e} ❌")
        
        # Check virtual environment
        print("\n🐍 Virtual Environment:")
        venv_path = self.project_dir / "venv"
        if venv_path.exists():
            print(f"   {venv_path} ✅")
        else:
            print("   Not found ❌")
        
        # Check .env file
        print("\n⚙️  Configuration:")
        env_path = self.project_dir / ".env"
        if env_path.exists():
            print("   .env file exists ✅")
            # Check for tokens
            with open(env_path) as f:
                content = f.read()
                has_discord = "DISCORD_BOT_TOKEN=" in content and "your_discord" not in content
                has_telegram = "TELEGRAM_BOT_TOKEN=" in content and "your_telegram" not in content
                
                if has_discord:
                    print("   Discord token configured ✅")
                else:
                    print("   Discord token not set ⚠️")
                
                if has_telegram:
                    print("   Telegram token configured ✅")
                else:
                    print("   Telegram token not set ⚠️")
        else:
            print("   .env file missing ❌")
        
        # Check database
        print("\n💾 Database:")
        db_path = self.project_dir / "data" / "bot.db"
        if db_path.exists():
            size = db_path.stat().st_size
            print(f"   {db_path} ({size} bytes) ✅")
        else:
            print("   Not created yet (will be created on first run)")
        
        # Check systemd service
        print("\n🔧 Systemd Service:")
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "youclaw"],
                capture_output=True,
                text=True
            )
            status = result.stdout.strip()
            if status == "active":
                print("   Running ✅")
            elif status == "inactive":
                print("   Stopped ⚠️")
            else:
                print(f"   Status: {status}")
        except Exception as e:
            print(f"   Not installed ⚠️")
        
        print("\n" + "=" * 50)
        return 0
    
    def cmd_status(self, args):
        """Show service status"""
        print("🦞 YouClaw Status\n")
        
        pid_file = Path("./data/youclaw.pid")
        
        if not pid_file.exists():
            print("Status: ⚪ Not Running")
            print("\nStart with: youclaw start")
            return 1
        
        try:
            pid = int(pid_file.read_text().strip())
            
            # Check if process is actually running
            os.kill(pid, 0)
            
            # Basic info only (simplified for reliability)
            print(f"Status: ✅ Running")
            print(f"PID: {pid}")
            print(f"\\n🔗 Dashboard: http://localhost:8080")
            return 0
                
        except (ProcessLookupError, ValueError):
            print("Status: ⚠️ Dead (PID file exists but process not found)")
            print("\nClean up with: youclaw stop")
            return 1
        except Exception as e:
            print(f"Status: ❌ Error: {e}")
            return 1
    
    def cmd_logs(self, args):
        """View logs"""
        print("🦞 YouClaw Logs (Ctrl+C to exit)\n")
        
        cmd = ["journalctl", "--user", "-u", "youclaw"]
        
        if args.follow:
            cmd.append("-f")
        
        if args.lines:
            cmd.extend(["-n", str(args.lines)])
        
        result = subprocess.run(cmd)
        return result.returncode
    
    async def run_wizard(self):
        """Interactive on-boarding wizard for YouClaw clones"""
        print("\n" + "🦞" * 10)
        print("WELCOME TO THE YOUCLAW NEURAL WIZARD")
        print("Preparing your personal AI Assistant for mission departure...")
        print("🦞" * 10 + "\n")

        print("[!] Tip: Press ENTER to skip any step and configure later via Dashboard.\n")

        # Helper to clean input (remove comments)
        def clean_input(prompt, default=None):
            val = input(prompt).strip()
            if '#' in val: val = val.split('#')[0].strip()
            return val or default

        # 🤖 Ollama Configuration
        print("🤖 Ollama AI Engine Configuration")
        ollama_host = clean_input("   - Ollama Host URL (default: http://localhost:11434): ", "http://localhost:11434")
        ollama_model = clean_input("   - Ollama Model (default: qwen2.5:1.5b-instruct): ", "qwen2.5:1.5b-instruct")
        
        # 🛰️ Telegram Setup
        print("\n🛰️ Telegram Bot Setup")
        tg_token = clean_input("   - Bot Token (from @BotFather): ", "")
        
        # 💬 Discord Setup
        print("\n💬 Discord Bot Setup")
        dc_token = clean_input("   - Bot Token (from Discord Dev Portal): ", "")
        
        # 🔍 Search Engine Setup
        print("\n🔍 Neural Search Engine")
        search_url = clean_input("   - Search URL (e.g. http://ip:8080/search): ", "")

        # 📧 Email Setup
        print("\n📧 Email Link Protocol")
        email_user = clean_input("   - Email Address: ", "")
        email_pass = clean_input("   - App Password (not your login password!): ", "")
        email_imap = clean_input("   - IMAP Host (default: imap.gmail.com): ", "imap.gmail.com")
        email_smtp = clean_input("   - SMTP Host (default: smtp.gmail.com): ", "smtp.gmail.com")

        # Write to .env with proper quoting
        env_path = Path(".env")
        env_content = [
            "# YouClaw Managed Configuration",
            f'OLLAMA_HOST="{ollama_host}"',
            f'OLLAMA_MODEL="{ollama_model}"',
            f'TELEGRAM_BOT_TOKEN="{tg_token}"',
            f'ENABLE_TELEGRAM="{"true" if tg_token else "false"}"',
            f'DISCORD_BOT_TOKEN="{dc_token}"',
            f'ENABLE_DISCORD="{"true" if dc_token else "false"}"',
            f'SEARCH_ENGINE_URL="{search_url or "http://localhost:8080/search"}"',
            f'EMAIL_USER="{email_user}"',
            f'EMAIL_PASSWORD="{email_pass}"',
            f'EMAIL_IMAP_HOST="{email_imap}"',
            f'EMAIL_SMTP_HOST="{email_smtp}"',
            f'ENABLE_EMAIL="{"true" if email_user else "false"}"',
            "DATABASE_PATH=./data/bot.db",
            "ADMIN_USER_IDENTITY=telegram:default"
        ]

        with open(env_path, "w") as f:
            f.write("\n".join(env_content))

        print("\n✨ Configuration Synced Successfully!")
        print("🔗 Mission Control will be available at: http://localhost:8080")
        print("🚀 Type 'youclaw start' to begin your AI journey.\n")

    async def cmd_start(self, args):
        """Start YouClaw service"""
        foreground = "--foreground" in args or "-f" in args
        
        if not Path(".env").exists():
            print("⚠️ No configuration found. Launching Neural Wizard...")
            await self.run_wizard()
            return 0

        # Check if already running
        pid_file = Path("./data/youclaw.pid")
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                # Check if process is actually running
                os.kill(pid, 0)
                print(f"⚠️ YouClaw is already running (PID: {pid})")
                print("   Use 'youclaw stop' first, or 'youclaw restart'")
                return 1
            except (ProcessLookupError, ValueError):
                # PID file exists but process is dead, clean it up
                pid_file.unlink()

        print(f"🦞 Starting YouClaw v4.8.4 in background...")
        
        if foreground:
            print("🦞 Starting YouClaw in foreground mode...")
            from .bot import main
            await main()
            return 0

        # Start as background daemon (Default)
        try:
            # import sys and os already at module level
            
            # Fork the process
            pid = os.fork()
            if pid > 0:
                # Parent process - save PID and exit
                pid_file.parent.mkdir(parents=True, exist_ok=True)
                pid_file.write_text(str(pid))
                print(f"✅ YouClaw started (PID: {pid})")
                print("🔗 Dashboard: http://localhost:8080")
                print("\nManage with:")
                print("  youclaw status   - Check status")
                print("  youclaw stop     - Stop service")
                print("  youclaw restart  - Restart service")
                return 0
            
            # Child process - become daemon
            os.setsid()  # Create new session
            
            # Redirect stdout/stderr to log file
            log_file = open("youclaw.log", "a")
            os.dup2(log_file.fileno(), sys.stdout.fileno())
            os.dup2(log_file.fileno(), sys.stderr.fileno())
            
            # Run the bot
            from .bot import main
            asyncio.run(main())
            
        except AttributeError:
            # Windows doesn't support fork, run in foreground
            print("🦞 Starting YouClaw (foreground mode on Windows)...")
            print("   Press Ctrl+C to stop")
            try:
                from .bot import main
                asyncio.run(main())
            except KeyboardInterrupt:
                print("\n👋 YouClaw stopped")
            return 0
        except Exception as e:
            print(f"❌ Launch Fault: {e}")
            return 1
    
    def cmd_stop(self, args):
        """Stop YouClaw service"""
        pid_file = Path("./data/youclaw.pid")
        
        if not pid_file.exists():
            print("⚠️ YouClaw is not running (no PID file found)")
            return 1
        
        try:
            pid = int(pid_file.read_text().strip())
            print(f"🦞 Stopping YouClaw (PID: {pid})...")
            
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)
            
            # Wait up to 10 seconds for process to stop
            import time
            for _ in range(10):
                try:
                    os.kill(pid, 0)  # Check if still running
                    time.sleep(1)
                except ProcessLookupError:
                    break
            
            # Force kill if still running
            try:
                os.kill(pid, 0)
                print("⚠️ Process didn't stop gracefully, forcing...")
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            
            pid_file.unlink()
            print("✅ YouClaw stopped")
            return 0
            
        except (ValueError, ProcessLookupError) as e:
            print(f"⚠️ Process not found, cleaning up PID file...")
            pid_file.unlink()
            return 1
        except Exception as e:
            print(f"❌ Error stopping YouClaw: {e}")
            return 1
    
    def cmd_restart(self, args):
        """Restart YouClaw service"""
        print("🦞 Restarting YouClaw...")
        self.cmd_stop(args)
        import time
        time.sleep(1)  # Brief pause
        return self.cmd_start(args)
    
    def cmd_dashboard(self, args):
        """Start web dashboard"""
        print("🦞 Starting YouClaw Dashboard...")
        print("   Dashboard will be available at http://localhost:8080")
        print("   Press Ctrl+C to stop\n")
        
        # Import and run dashboard
        try:
            from dashboard import run_dashboard
            asyncio.run(run_dashboard(port=args.port))
        except ImportError as e:
            print(f"❌ Dashboard module not found. Make sure dashboard.py exists. Error: {e}")
            return 1
        except KeyboardInterrupt:
            print("\n👋 Dashboard stopped")
            return 0
    
    def cmd_uninstall(self, args):
        """Uninstall YouClaw"""
        print("🦞 YouClaw Unmet protocol initiated...")
        confirm = input("Are you sure you want to remove YouClaw configuration and data? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Cancelled.")
            return 0
        
        # Stop service
        self.cmd_stop(args)
        
        # Remove data
        try:
            import shutil
            data_dir = self.project_dir / "data"
            if data_dir.exists():
                print(f"🗑️ Removing {data_dir}...")
                shutil.rmtree(data_dir)
            
            for file in ["youclaw.log", "bot_output.log", ".env"]:
                fpath = Path(file)
                if fpath.exists():
                    print(f"🗑️ Removing {fpath}...")
                    fpath.unlink()
                    
            print("\n✅ Data and configuration cleared.")
            print("To complete the uninstallation, please run:")
            print("\n    pip uninstall youclaw\n")
            return 0
        except Exception as e:
            print(f"❌ Error cleaning up: {e}")
            return 1
    
    def run(self):
        """Main CLI entry point"""
        parser = argparse.ArgumentParser(
            description="YouClaw - Your Personal AI Assistant",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  youclaw install          # Run installation
  youclaw check            # Health check
  youclaw start            # Start service
  youclaw logs -f          # Follow logs
  youclaw dashboard        # Start web dashboard
            """
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
        
        # Install command
        subparsers.add_parser("install", help="Run installation script")
        
        # Check command
        subparsers.add_parser("check", help="Run health checks")
        
        # Status command
        subparsers.add_parser("status", help="Show service status")
        
        # Logs command
        logs_parser = subparsers.add_parser("logs", help="View logs")
        logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
        logs_parser.add_argument("-n", "--lines", type=int, default=50, help="Number of lines to show")
        
        # Start command
        subparsers.add_parser("start", help="Start YouClaw service")
        
        # Stop command
        subparsers.add_parser("stop", help="Stop YouClaw service")
        
        # Restart command
        subparsers.add_parser("restart", help="Restart YouClaw service")
        
        # Dashboard command
        dashboard_parser = subparsers.add_parser("dashboard", help="Start web dashboard")
        dashboard_parser.add_argument("-p", "--port", type=int, default=8080, help="Dashboard port")
        
        # Uninstall command
        subparsers.add_parser("uninstall", help="Uninstall YouClaw and clean up data")
        
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return 0
        
        # Execute command
        command_map = {
            "install": self.cmd_install,
            "check": self.cmd_check,
            "status": self.cmd_status,
            "logs": self.cmd_logs,
            "start": self.cmd_start,
            "stop": self.cmd_stop,
            "restart": self.cmd_restart,
            "dashboard": self.cmd_dashboard,
            "uninstall": self.cmd_uninstall,
        }
        
        if args.command in command_map:
            res = command_map[args.command](args)
            if asyncio.iscoroutine(res):
                return asyncio.run(res)
            return res
        else:
            print(f"Unknown command: {args.command}")
            return 1


def main():
    cli = YouClawCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()
