"""
YouClaw Core Skills
A collection of built-in tools for the bot.
"""

import os
import subprocess
import logging
import imaplib
import smtplib
import email
from email.message import EmailMessage
from datetime import datetime, timedelta
from .config import config
from .skills_manager import skill_manager
from .scheduler_manager import scheduler_manager
from .search_client import search_client

logger = logging.getLogger(__name__)

@skill_manager.skill(name="list_emails", description="Check for unread emails in your inbox.")
def list_emails(limit: int = 5) -> str:
    """Connects to the IMAP server and retrieves a summary of the latest unread emails."""
    if not config.email.enabled:
        return "Email protocol is currently deactivated. Please enable it in the Control Center."
    
    try:
        # Connect to IMAP
        mail = imaplib.IMAP4_SSL(config.email.imap_host, config.email.imap_port)
        mail.login(config.email.user, config.email.password)
        mail.select("inbox")
        
        # Search for unread emails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            return "Failed to search neural streams for messages."
            
        email_ids = messages[0].split()
        if not email_ids:
            return "No unread messages found in your neural inbox."
            
        results = []
        # Get the latest 'limit' emails
        for e_id in reversed(email_ids[-limit:]):
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = msg["subject"]
                    sender = msg["from"]
                    results.append(f"FROM: {sender}\nSUBJECT: {subject}")
        
        mail.logout()
        summary = "\n\n".join(results)
        return f"Found {len(email_ids)} unread messages. Here are the latest {len(results)}:\n\n{summary}"
        
    except Exception as e:
        logger.error(f"IMAP Error: {e}")
        return f"Protocol Fault during IMAP handshake: {str(e)}"

@skill_manager.skill(name="send_email", description="Send an email to a specific recipient.")
def send_email(to_address: str, subject: str, body: str) -> str:
    """Connects to the SMTP server and transmits a new email message."""
    if not config.email.enabled:
        return "Email protocol is currently deactivated. Please enable it in the Control Center."
    
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = config.email.user
        msg['To'] = to_address
        
        # Connect to SMTP
        with smtplib.SMTP(config.email.smtp_host, config.email.smtp_port) as server:
            server.starttls()
            server.login(config.email.user, config.email.password)
            server.send_message(msg)
            
        return f"Message successfully transmitted to {to_address}."
    except Exception as e:
        logger.error(f"SMTP Error: {e}")
        return f"Protocol Fault during SMTP transmission: {str(e)}"

# Removed as per user request (small model limitations)
# @skill_manager.skill(name="web_search", description="Search the internet for real-time information, news, or specific facts.")
# async def web_search(query: str) -> str:
#     """Useful for answering questions about current events or finding information not in training data."""
#     return await search_client.search(query)

@skill_manager.skill(name="read_file", description="Read the contents of a file on the server.", admin_only=True)
def read_file(file_path: str) -> str:
    """Reads a file and returns its content. Use this to examine logs, configs, or data files."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        
        # Limit file size for safety (1MB)
        if os.path.getsize(file_path) > 1024 * 1024:
            return "Error: File is too large to read (max 1MB)."
            
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@skill_manager.skill(name="shell_command", description="DANGEROUS: Execute a bash command on the server. Use with extreme caution.", admin_only=True)
def shell_command(command: str) -> str:
    """Executes a system command and returns the output (stdout and stderr)."""
    try:
        logger.warning(f"Executing shell command: {command}")
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        output = result.stdout
        if result.stderr:
            output += f"\nErrors:\n{result.stderr}"
        return output or "Command executed successfully (no output)."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 10 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"

@skill_manager.skill(name="schedule_reminder", description="Schedule a reminder for the user at a specific time.")
async def schedule_reminder(message: str, minutes_from_now: int, platform: str, user_id: str) -> str:
    """Useful for setting timers or reminders. The bot will message the user proactively."""
    run_date = datetime.now() + timedelta(minutes=minutes_from_now)
    await scheduler_manager.add_notification_job(
        platform=platform,
        user_id=user_id,
        message=f"⏰ REMINDER: {message}",
        run_date=run_date
    )
    return f"I've scheduled your reminder for '{message}' in {minutes_from_now} minutes."

@skill_manager.skill(name="store_secret", description="Securely store a personal secret (like an API key).")
async def store_secret(key: str, value: str, platform: str, user_id: str) -> str:
    """Useful for when the user provides a token or key that they want the bot to remember for future actions.
    The secret is stored ONLY for this specific user on this platform."""
    from .memory_manager import memory_manager
    await memory_manager.set_user_secret(platform, user_id, key, value)
    return f"I've securely stored your '{key}' secret."
@skill_manager.skill(name="run_python_code", description="Execute arbitrary Python code on the server.", admin_only=True)
def run_python_code(code: str) -> str:
    """Executes Python code and returns the result of the last expression or printed output."""
    try:
        # Create a temporary script to run
        with open('temp_script.py', 'w') as f:
            f.write(code)
        
        result = subprocess.run(
            ['python3', 'temp_script.py'],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        os.remove('temp_script.py')
        
        output = result.stdout
        if result.stderr:
            output += f"\nErrors:\n{result.stderr}"
        return output or "Code executed successfully (no output)."
    except Exception as e:
        return f"Error executing Python code: {str(e)}"
@skill_manager.skill(name="synthesize_new_skill", description="Permanently save code as a NEW bot skill.", admin_only=True)
def synthesize_new_skill(skill_name: str, description: str, code: str) -> str:
    """Save the code to dynamic_skills/ folder so it can be used in future conversations."""
    try:
        # Sanitize skill name
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '', skill_name).lower()
        if not safe_name:
            return "Error: Invalid skill name."
            
        file_path = os.path.join('dynamic_skills', f"{safe_name}.py")
        
        # Format as a proper skill module
        module_content = (
            'from skills_manager import skill_manager\n\n'
            f'@skill_manager.skill(name="{safe_name}", description="{description}")\n'
            f'def {safe_name}(**kwargs):\n'
            f'    """{description}"""\n'
            '    # Synthesized Code:\n'
            '    ' + code.replace('\n', '\n    ') + '\n'
        )
        
        with open(file_path, 'w') as f:
            f.write(module_content)
        
        return f"Successfully synthesized new skill: {safe_name}. I can now use it in future tasks!"
    except Exception as e:
        return f"Error synthesizing skill: {str(e)}"

@skill_manager.skill(name="watch_url", description="Set up a watchdog to monitor a URL for changes or status. The bot will alert you if the status changes.")
async def watch_url(url: str, interval_minutes: int, platform: str, user_id: str) -> str:
    """Useful for monitoring websites, servers, or APIs. Example: 'Watch https://google.com every 5 minutes'."""
    job_id = f"watch_{user_id}_{hash(url)}"
    await scheduler_manager.add_watcher_job(
        platform=platform,
        user_id=user_id,
        target_url=url,
        interval_minutes=interval_minutes,
        job_id=job_id
    )
    return f"I've set up a watchdog for {url}. I'll check it every {interval_minutes} minutes and alert you if I see issues."
