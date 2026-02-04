"""
YouClaw CLI - Command Line Interface
Provides commands for installation, health checks, and management.
"""

import sys
import subprocess
import os
import asyncio
import argparse
from pathlib import Path

# Add parent directory to path for imports
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
        result = subprocess.run(
            ["systemctl", "--user", "status", "youclaw"],
            capture_output=False
        )
        return result.returncode
    
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
    
    def cmd_start(self, args):
        """Start YouClaw service"""
        print("🦞 Starting YouClaw...")
        result = subprocess.run(["systemctl", "--user", "start", "youclaw"])
        if result.returncode == 0:
            print("✅ YouClaw started")
        return result.returncode
    
    def cmd_stop(self, args):
        """Stop YouClaw service"""
        print("🦞 Stopping YouClaw...")
        result = subprocess.run(["systemctl", "--user", "stop", "youclaw"])
        if result.returncode == 0:
            print("✅ YouClaw stopped")
        return result.returncode
    
    def cmd_restart(self, args):
        """Restart YouClaw service"""
        print("🦞 Restarting YouClaw...")
        result = subprocess.run(["systemctl", "--user", "restart", "youclaw"])
        if result.returncode == 0:
            print("✅ YouClaw restarted")
        return result.returncode
    
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
        }
        
        if args.command in command_map:
            return command_map[args.command](args)
        else:
            print(f"Unknown command: {args.command}")
            return 1


def main():
    cli = YouClawCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()
