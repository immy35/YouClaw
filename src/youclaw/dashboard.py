"""
YouClaw Web Dashboard
Web interface for monitoring and managing YouClaw.
"""

from aiohttp import web
import aiohttp_jinja2
import jinja2
import json
import asyncio
import os
from pathlib import Path
from datetime import datetime
from .ollama_client import ollama_client
from .memory_manager import memory_manager
from .skills_manager import skill_manager
from .scheduler_manager import scheduler_manager
from .env_manager import env_manager

from .config import config
import logging

logger = logging.getLogger(__name__)

# Dashboard routes
routes = web.RouteTableDef()

async def verify_session(request):
    """Verify X-Session-Token against stored credentials"""
    username = request.headers.get('X-Session-User')
    token = request.headers.get('X-Session-Token')
    if not username or not token: return None
    
    async with memory_manager.db.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,)) as cursor:
        row = await cursor.fetchone()
        if row:
            pw_hash, role = row
            import hashlib
            from .config import config
            expected_token = hashlib.sha256(f"{username}{pw_hash}{config.bot.prefix}".encode()).hexdigest()
            if token == expected_token:
                return {"username": username, "role": role}
    return None

async def get_user_identity(request):
    """Get the linked platform:id for the current session user + token verification"""
    auth = await verify_session(request)
    if not auth: return None, None
    
    platform, user_id = await memory_manager.get_linked_identity(auth['username'])
    return platform, user_id

async def check_admin(request):
    """Check if the session user is an admin + token verification"""
    auth = await verify_session(request)
    # Universal Admin: If you can login, you are the owner.
    return auth is not None


@routes.get('/')
async def serve_html(request):
    return web.Response(
        text=DASHBOARD_HTML, 
        content_type='text/html',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'}
    )


@routes.post('/api/auth/register')
async def api_register(request):
    """Register a new dashboard account"""
    try:
        data = await request.json()
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return web.json_response({"error": "Username and password required"}, status=400)
        
        success = await memory_manager.create_user(username, password)
        if success:
            return web.json_response({"success": True})
        return web.json_response({"error": "Username already exists"}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/auth/login')
async def api_login(request):
    """Login and return user info"""
    try:
        data = await request.json()
        user = await memory_manager.verify_user(data.get('username'), data.get('password'))
        if user:
            return web.json_response({"success": True, "user": user})
        return web.json_response({"error": "Invalid credentials"}, status=401)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/auth/link')
async def api_link_account(request):
    """Link dashboard account to bot platform identity"""
    try:
        username = request.headers.get('X-Session-User')
        if not username: return web.json_response({"error": "Auth Required"}, status=401)
        
        data = await request.json()
        platform = data.get('platform')
        user_id = data.get('user_id')
        
        if not platform or not user_id:
            return web.json_response({"error": "Platform and ID required"}, status=400)
            
        await memory_manager.link_account(username, platform, user_id)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/stats')
async def api_stats(request):
    """Get bot statistics for current user"""
    try:
        platform, user_id = await get_user_identity(request)
        is_admin = await check_admin(request)
        
        if not user_id and not is_admin:
            return web.json_response({"error": "Account not linked to a bot platform"}, status=403)
        
        # Get memory stats for this user if linked
        count = 0
        if user_id:
            async with memory_manager.db.execute(
                "SELECT COUNT(*) FROM conversations WHERE platform=? AND user_id=?", 
                (platform, user_id)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            
        # Get global stats
        async with memory_manager.db.execute("SELECT COUNT(*) FROM conversations") as cursor:
            total_messages = (await cursor.fetchone())[0]
        async with memory_manager.db.execute("SELECT COUNT(DISTINCT user_id) FROM conversations") as cursor:
            unique_users = (await cursor.fetchone())[0]
            
        # Calculate uptime (simplified to avoid psutil issues)
        import time, os
        try:
            # Just show process start time relative to now if possible, 
            # but without psutil we can't easily get start time cross-platform.
            # We will skip uptime or assume 0 for stability.
            uptime_str = "Running"
        except:
            uptime_str = "Unknown"

        from .personality_manager import PERSONALITIES, DEFAULT_PERSONALITY
        active_p = await memory_manager.get_global_setting("active_personality", DEFAULT_PERSONALITY)
        personality_name = PERSONALITIES.get(active_p, PERSONALITIES[DEFAULT_PERSONALITY])['name']
        
        try:
            import asyncio
            # Force 3-second timeout for dashboard responsiveness
            ollama_health = await asyncio.wait_for(ollama_client.check_health(), timeout=2.0)
        except:
            ollama_health = False
        
        stats = {
            "version": "4.9.10",
            "status": "online",
            "uptime": uptime_str,
            "ollama_connected": ollama_health,
            "ollama_model": ollama_client.model if ollama_health else "Disconnected (Check URL)",
            "telegram_enabled": config.telegram.enabled,
            "discord_enabled": config.discord.enabled,
            "timestamp": datetime.now().isoformat(),
            "user_messages": total_messages,
            "unique_users": unique_users,
            "active_personality": personality_name,
            "user_identity": f"{platform}:{user_id}" if user_id else "Guest",
            "is_linked": bool(user_id),
            "model": ollama_client.model if ollama_health else "Disconnected",
            "is_admin": is_admin
        }
        
        if is_admin:
            try:
                stats["available_models"] = await ollama_client.get_available_models()
            except:
                stats["available_models"] = []
            
        return web.json_response(stats)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/conversations')
async def api_conversations(request):
    """Get recent conversations for current user"""
    try:
        platform, user_id = await get_user_identity(request)
        if not user_id: return web.json_response({"conversations": []})

        async with memory_manager.db.execute("""
            SELECT platform, user_id, channel_id, 
                   MAX(timestamp) as last_message,
                   COUNT(*) as message_count
            FROM conversations
            WHERE platform=? AND user_id=?
            GROUP BY channel_id
            ORDER BY last_message DESC
            LIMIT 50
        """, (platform, user_id)) as cursor:
            rows = await cursor.fetchall()
            conversations = [{"platform": r[0], "user_id": r[1], "channel_id": r[2], "last_message": r[3], "message_count": r[4]} for r in rows]
            return web.json_response({"conversations": conversations})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/skills')
async def api_skills(request):
    """Get available skills"""
    skills = skill_manager.get_all_skills()
    return web.json_response({"skills": skills})


@routes.get('/api/jobs')
async def api_get_jobs(request):
    """Get jobs belonging to the current user"""
    try:
        platform, user_id = await get_user_identity(request)
        if not user_id: return web.json_response({"jobs": []})
        
        jobs = []
        for job in scheduler_manager.scheduler.get_jobs():
            if len(job.args) >= 2 and job.args[0] == platform and job.args[1] == user_id:
                jobs.append({
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "prompt": job.args[2] if len(job.args) > 2 else "Mission"
                })
        return web.json_response({"jobs": jobs})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/jobs/schedule')
async def api_schedule_job(request):
    """Schedule a new AI Cron Job for the current user"""
    try:
        req_platform, req_user_id = await get_user_identity(request)
        if not req_user_id: return web.json_response({"error": "Account linking required"}, status=403)
        
        data = await request.json()
        prompt = data.get('prompt')
        frequency = data.get('frequency', '60')
        channel = data.get('channel', req_platform) # Default to user's platform
        
        if not prompt:
            return web.json_response({"error": "Prompt required"}, status=400)
        
        import hashlib
        job_id = f"cron_{hashlib.md5(f'{req_user_id}{prompt}{channel}'.encode()).hexdigest()[:8]}"
        cron_expr = f"*/{frequency} * * * *" if int(frequency) < 60 else f"0 */{int(int(frequency)/60)} * * *"
        
        await scheduler_manager.add_ai_cron_job(channel, req_user_id, prompt, cron_expr, job_id)
        return web.json_response({"success": True, "job_id": job_id})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/jobs/delete')
async def api_delete_job(request):
    """Cancel a user's job"""
    try:
        platform, user_id = await get_user_identity(request)
        data = await request.json()
        job_id = data.get('job_id')
        
        job = scheduler_manager.scheduler.get_job(job_id)
        if job and len(job.args) >= 2 and job.args[0] == platform and job.args[1] == user_id:
            scheduler_manager.scheduler.remove_job(job_id)
            return web.json_response({"success": True})
        return web.json_response({"error": "Unauthorized or not found"}, status=403)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/system/personality')
async def api_get_personality(request):
    """Get list of personalities and current active one"""
    from .personality_manager import PERSONALITIES, DEFAULT_PERSONALITY
    active = await memory_manager.get_global_setting("active_personality", DEFAULT_PERSONALITY)
    return web.json_response({
        "personalities": PERSONALITIES,
        "active": active
    })


@routes.post('/api/system/personality')
async def api_set_personality(request):
    """Admin Only: Switch personality"""
    if not await check_admin(request): return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        data = await request.json()
        key = data.get('personality')
        from .personality_manager import PERSONALITIES
        if key in PERSONALITIES:
            await memory_manager.set_global_setting("active_personality", key)
            return web.json_response({"success": True})
        return web.json_response({"error": "Invalid personality"}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/system/env')
async def api_get_env(request):
    """Admin Only: Get current tokens"""
    if not await check_admin(request): return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        env_vars = env_manager.get_all()
        return web.json_response({
            "telegram_token": env_vars.get("TELEGRAM_BOT_TOKEN") or config.telegram.token or "",
            "discord_token": env_vars.get("DISCORD_BOT_TOKEN") or config.discord.token or "",
            "search_url": env_vars.get("SEARCH_ENGINE_URL") or config.search_url,
            "ollama_url": env_vars.get("OLLAMA_HOST") or config.ollama.host,
            "email": {
                "imap_host": config.email.imap_host,
                "imap_port": config.email.imap_port,
                "smtp_host": config.email.smtp_host,
                "smtp_port": config.email.smtp_port,
                "user": config.email.user,
                "enabled": config.email.enabled
            }
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/system/secrets')
async def api_save_system_secrets(request):
    """Admin Only: Update tokens"""
    if not await check_admin(request): return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        data = await request.json()
        if 'telegram_token' in data:
            val = data['telegram_token']
            env_manager.set_key("TELEGRAM_BOT_TOKEN", val)
            await memory_manager.set_global_setting("telegram_token", val)
        if 'discord_token' in data:
            val = data['discord_token']
            env_manager.set_key("DISCORD_BOT_TOKEN", val)
            await memory_manager.set_global_setting("discord_token", val)
        if 'search_url' in data:
            val = data['search_url']
            env_manager.set_key("SEARCH_ENGINE_URL", val)
            await memory_manager.set_global_setting("search_url", val)
            
        ollama_status = "unchanged"
        if 'ollama_url' in data:
            val = data['ollama_url']
            env_manager.set_key("OLLAMA_HOST", val)
            await memory_manager.set_global_setting("ollama_host", val)
            
            # Instant validation
            await config.refresh_from_db()
            await ollama_client.initialize() # Re-init with new URL
            try:
                import asyncio
                is_online = await asyncio.wait_for(ollama_client.check_health(), timeout=2.0)
                ollama_status = "online" if is_online else "offline"
            except:
                ollama_status = "offline"
        
        # Email Secrets
        if 'email' in data:
            e = data['email']
            if 'imap_host' in e: await memory_manager.set_global_setting("email_imap_host", e['imap_host'])
            if 'imap_port' in e: await memory_manager.set_global_setting("email_imap_port", str(e['imap_port']))
            if 'smtp_host' in e: await memory_manager.set_global_setting("email_smtp_host", e['smtp_host'])
            if 'smtp_port' in e: await memory_manager.set_global_setting("email_smtp_port", str(e['smtp_port']))
            if 'user' in e: await memory_manager.set_global_setting("email_user", e['user'])
            if 'password' in e: await memory_manager.set_global_setting("email_password", e['password'])

        await config.refresh_from_db()
            
        bot_instance = request.app.get('bot')
        if bot_instance: asyncio.create_task(bot_instance.restart_handlers())
        bot_instance = request.app.get('bot')
        if bot_instance: asyncio.create_task(bot_instance.restart_handlers())
        return web.json_response({"success": True, "ollama_status": ollama_status})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/system/toggle_channel')
async def api_toggle_channel(request):
    """Admin Only: Toggle Telegram/Discord connectivity"""
    if not await check_admin(request): return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        data = await request.json()
        channel = data.get('channel') 
        enabled = data.get('enabled') 
        
        if channel not in ['telegram', 'discord', 'email']:
            return web.json_response({"error": "Invalid channel"}, status=400)
            
        await memory_manager.set_global_setting(f"{channel}_enabled", "true" if enabled else "false")
        await config.refresh_from_db()
        
        bot_instance = request.app.get('bot')
        if bot_instance: asyncio.create_task(bot_instance.restart_handlers())
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/memory/clear')
async def api_clear_memory(request):
    """User: Clear own memory"""
    try:
        platform, user_id = await get_user_identity(request)
        if not user_id: return web.json_response({"error": "Linking Required"}, status=403)
        
        await memory_manager.db.execute("DELETE FROM conversations WHERE platform=? AND user_id=?", (platform, user_id))
        await memory_manager.db.commit()
        return web.json_response({"success": True, "message": "Personal memory cleared!"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get('/api/chat/stream')
async def api_chat_stream(request):
    """Streaming dashboard-to-model chat"""
    try:
        username = request.query.get('user')
        message = request.query.get('message')
        force_search = request.query.get('search') == 'true'
        
        if not username or not message: return web.Response(text="Error: Missing params", status=400)
        
        auth = await verify_session(request)
        if not auth or auth['username'] != username:
            return web.Response(text="Error: Unauthorized session scope", status=403)
        
        platform, user_id = await memory_manager.get_linked_identity(username)
        ctx = {"platform": platform or "dashboard", "user_id": user_id or f"dash_{username}"}
        history = await memory_manager.get_conversation_history(ctx["platform"], ctx["user_id"])
        
        await memory_manager.add_message(ctx["platform"], ctx["user_id"], "user", message)
        profile = await memory_manager.get_user_profile(ctx["platform"], ctx["user_id"])
        if not profile.get("name"): profile["name"] = username

        response = web.StreamResponse(status=200, reason='OK', headers={'Content-Type': 'text/plain'})
        await response.prepare(request)

        full_response = ""
        # Use ReAct streaming with tools
        async for chunk in ollama_client.chat_with_tools_stream(
            messages=history + [{"role": "user", "content": message}],
            user_profile=profile,
            context=ctx
        ):
            await response.write(chunk.encode())
            full_response += chunk
        
        if "[SECURITY_INTERCEPT]" in full_response:
             # We don't save the intercept raw string to conversation history 
             # because it's a protocol internal, but we want the UI to see it.
             pass
        else:
             await memory_manager.add_message(ctx["platform"], ctx["user_id"], "assistant", full_response)
             
        await response.write_eof()
        return response
    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(text=f"Protocol Fault: {str(e)}", status=500)


@routes.post('/api/security/approve')
async def api_security_approve(request):
    """Confirm execution of an intercepted command from the web"""
    try:
        data = await request.json()
        req_id = data.get('request_id')
        action = data.get('action') # 'approve' or 'deny'
        
        if action == "approve":
            result = await skill_manager.confirm_execution(req_id)
            return web.json_response({"success": True, "result": result})
        else:
            if req_id in skill_manager.pending_approvals:
                del skill_manager.pending_approvals[req_id]
            return web.json_response({"success": True, "message": "Denied"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post('/api/model/switch')
async def api_switch_model(request):
    """Admin Only: Switch model"""
    if not await check_admin(request): return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        data = await request.json()
        model_name = data.get('model')
        success = await ollama_client.switch_model(model_name)
        if success:
            await memory_manager.set_global_setting("active_model", model_name)
        return web.json_response({"success": success})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouClaw V4.9.5 | Justice Neural Hub 🦞</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {
            --bg: #050510;
            --surface: rgba(17, 24, 39, 0.7);
            --surface-hover: rgba(31, 41, 55, 0.85);
            --border: rgba(255, 255, 255, 0.1);
            --text-main: #ffffff;
            --text-dim: #94a3b8;
            --primary: #8b5cf6;
            --accent: #d946ef;
            --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --glass: blur(30px) saturate(180%);
            --sidebar-width: 300px;
            --bubble-user: var(--primary-gradient);
            --bubble-ai: rgba(255, 255, 255, 0.05);
            --nav-glow: 0 0 20px rgba(139, 92, 246, 0.4);
            --primary-glow: rgba(139, 92, 246, 0.3);
            --secondary: #10b981;
            --danger: #ef4444;
            --card-shadow: 0 20px 50px -12px rgba(0, 0, 0, 0.5);
        }

        [data-theme="light"] {
            --bg: #f8fafc;
            --surface: rgba(255, 255, 255, 0.9);
            --surface-hover: #ffffff;
            --border: rgba(0, 0, 0, 0.1);
            --text-main: #0f172a;
            --text-dim: #64748b;
            --primary: #6366f1;
            --accent: #d946ef;
            --bubble-user: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            --bubble-ai: #ffffff;
            --primary-glow: rgba(99, 102, 241, 0.2);
            --glass: blur(10px);
            --input-bg: rgba(0, 0, 0, 0.03);
            --input-area-bg: rgba(0, 0, 0, 0.02);
        }

        :root {
            --input-bg: rgba(255, 255, 255, 0.05);
            --input-area-bg: rgba(0, 0, 0, 0.2);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            overflow: hidden;
            transition: all 0.4s ease;
        }

        .sidebar {
            width: var(--sidebar-width);
            height: 100vh;
            background: var(--surface);
            backdrop-filter: var(--glass);
            border-right: 1px solid var(--border);
            padding: 40px 24px;
            display: flex;
            flex-direction: column;
            gap: 40px;
            z-index: 100;
        }
        .sidebar-logo { font-size: 1.5rem; font-weight: 800; letter-spacing: -1px; margin-bottom: 20px; }
        .nav-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
        .nav-item { 
            padding: 16px 20px; border-radius: 16px; cursor: pointer; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex; align-items: center; gap: 16px; font-weight: 700; color: var(--text-dim);
            border: 1px solid transparent;
        }
        .nav-item i { font-style: normal; font-size: 1.2rem; filter: grayscale(1); transition: 0.3s; }
        .nav-item:hover { background: var(--border); color: var(--text-main); transform: translateX(5px); }
        .nav-item:hover i { filter: grayscale(0); transform: scale(1.1); }
        .nav-item.active { 
            background: var(--primary); color: white; border-color: rgba(255,255,255,0.1);
            box-shadow: 0 10px 30px var(--primary-glow); 
        }
        .nav-item.active i { filter: grayscale(0); }

        .main-stage {
            flex: 1;
            height: 100vh;
            overflow-y: auto;
            position: relative;
            background: radial-gradient(at 0% 0%, var(--primary-glow) 0px, transparent 50%);
        }

        .container { 
            max-width: 1400px; margin: 0 auto; padding: 48px; 
            opacity: 0; transform: translateY(10px); transition: all 0.6s ease; 
        }
        .container.active { opacity: 1; transform: translateY(0); }

        .auth-portal {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(2, 6, 23, 0.7); backdrop-filter: blur(40px);
            z-index: 10000; display: flex; align-items: center; justify-content: center;
        }
        .auth-card { background: var(--surface); border: 1px solid var(--border); padding: 48px; border-radius: 40px; width: 100%; max-width: 440px; text-align: center; }

        .header-bar {
            display: flex; justify-content: flex-end; align-items: center; gap: 24px;
            margin-bottom: 40px; padding: 0 0 20px 0; border-bottom: 1px solid var(--border);
        }

        .dashboard-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 32px; }
        .card { 
            background: var(--surface); backdrop-filter: var(--glass); border: 1px solid var(--border); 
            border-radius: 32px; padding: 32px; box-shadow: var(--card-shadow); transition: all 0.3s ease;
        }
        .card:hover { border-color: var(--primary); }
        .card-title { font-size: 1.1rem; font-weight: 800; margin-bottom: 24px; display: flex; align-items: center; gap: 12px; }

        .btn { 
            padding: 16px; border-radius: 16px; font-weight: 800; font-size: 0.9rem; 
            cursor: pointer; border: none; transition: all 0.3s ease; font-family: inherit;
            display: flex; align-items: center; justify-content: center; gap: 10px;
        }
        .btn-primary { background: var(--primary); color: white; box-shadow: 0 4px 12px var(--primary-glow); }
        .btn-outline { background: transparent; border: 2px solid var(--border); color: var(--text-main); }

        .input-group { margin-bottom: 20px; }
        .input-label { display: block; font-size: 0.75rem; color: var(--text-dim); margin-bottom: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
        .text-input { 
            width: 100%; background: rgba(0, 0, 0, 0.05); border: 1px solid var(--border); 
            border-radius: 16px; padding: 14px 20px; color: var(--text-main); font-family: inherit;
        }

        .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
        .stat-item { background: rgba(124, 58, 237, 0.05); padding: 24px; border-radius: 24px; text-align: center; border: 1px solid var(--border); }
        .stat-val { font-size: 2rem; font-weight: 800; }

        .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { 
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; 
            background-color: var(--border); transition: .4s; border-radius: 34px; 
        }
        .slider:before { 
            position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; 
            background-color: white; transition: .4s; border-radius: 50%; 
        }
        input:checked + .slider { background-color: var(--secondary); }
        input:checked + .slider:before { transform: translateX(20px); }

        #neural-terminal-view { display: none; padding: 20px; height: 100%; }
        .chat-layout { height: 100%; display: grid; grid-template-columns: 1fr 340px; gap: 32px; max-width: 1600px; margin: 0 auto; }
        
        .chat-main { 
            display: flex; flex-direction: column; background: var(--surface); 
            border: 1px solid var(--border); border-radius: 40px; 
            box-shadow: 0 30px 60px -12px rgba(0,0,0,0.5);
            overflow: hidden; backdrop-filter: var(--glass);
        }
        
        #chat-messages { 
            flex: 1; overflow-y: auto; padding: 40px; display: flex; 
            flex-direction: column; gap: 32px; scroll-behavior: smooth;
            background: radial-gradient(circle at top right, rgba(139, 92, 246, 0.05), transparent 40%);
        }
        
        .msg { 
            max-width: 75%; padding: 20px 28px; border-radius: 28px; line-height: 1.7; 
            font-size: 1rem; position: relative; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            animation: msgEnter 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        @keyframes msgEnter { from { opacity: 0; transform: translateY(20px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
        
        .msg-user { 
            align-self: flex-end; background: var(--bubble-user); color: white; 
            border-bottom-right-radius: 4px; box-shadow: 0 15px 30px rgba(139, 92, 246, 0.3);
            font-weight: 500;
        }
        
        .msg-ai { 
            align-self: flex-start; background: var(--bubble-ai); color: var(--text-main); 
            border-bottom-left-radius: 4px; border: 1px solid var(--border);
            backdrop-filter: blur(10px); box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        
        .chat-input-area { 
            padding: 30px 40px; background: var(--input-area-bg); 
            border-top: 1px solid var(--border); display: flex; gap: 20px; align-items: center;
        }
        
        .chat-field {
            flex: 1; background: var(--input-bg); border: 1px solid var(--border);
            border-radius: 20px; padding: 18px 24px; color: var(--text-main); font-family: inherit;
            font-size: 1rem; transition: 0.3s;
        }
        .chat-field:focus { border-color: var(--primary); outline: none; background: rgba(255,255,255,0.08); box-shadow: 0 0 20px var(--primary-glow); }
        
        .pulse {
            width: 8px; height: 8px; background: var(--accent); border-radius: 50%;
            display: inline-block; margin-right: 8px; box-shadow: 0 0 10px var(--accent);
            animation: synapticPulse 1.5s infinite;
        }
        @keyframes synapticPulse { 0% { opacity: 0.3; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.2); } 100% { opacity: 0.3; transform: scale(0.8); } }
        
        .send-btn {
            width: 56px; height: 56px; border-radius: 20px; background: var(--primary-gradient);
            border: none; color: white; cursor: pointer; display: flex; align-items: center;
            justify-content: center; font-size: 1.2rem; transition: 0.3s;
            box-shadow: 0 10px 20px var(--primary-glow);
        }
        .send-btn:hover { transform: scale(1.05) rotate(5deg); box-shadow: 0 15px 30px var(--primary-glow); }
        .send-btn:disabled { opacity: 0.5; cursor: wait; }
        .p-pill { 
            padding: 10px 18px; border-radius: 14px; background: rgba(0,0,0,0.1); 
            border: 1px solid var(--border); cursor: pointer; transition: all 0.3s;
            font-size: 0.8rem; font-weight: 700; color: var(--text-dim);
        }
        .p-pill:hover { border-color: var(--primary); color: var(--text-main); }
        .p-pill.active { background: var(--primary); color: white; border-color: var(--primary); box-shadow: 0 4px 12px var(--primary-glow); }

        .dot { 
            width: 5px; height: 5px; background: var(--primary); border-radius: 50%; 
            opacity: 0.6; box-shadow: 0 0 8px var(--primary);
            animation: pulse-neon 1.5s infinite ease-in-out; 
        }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes pulse-neon { 
            0%, 100% { transform: scale(1); opacity: 0.4; box-shadow: 0 0 2px var(--primary); } 
            50% { transform: scale(1.4); opacity: 1; box-shadow: 0 0 12px var(--primary); } 
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

        .eye-btn {
            position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
            background: none; border: none; cursor: pointer; font-size: 1.2rem;
            opacity: 0.6; transition: opacity 0.2s;
        }
        .eye-btn:hover { opacity: 1; }

        #web-search-toggle { transition: all 0.3s; border: 1px solid var(--border); }
        #web-search-toggle.active { background: rgba(0, 255, 157, 0.2); color: var(--secondary); border-color: var(--secondary); box-shadow: 0 0 10px rgba(0,255,157,0.2); }

        .channel-group { 
            background: rgba(255, 255, 255, 0.02); padding: 20px; border-radius: 20px; border: 1px solid var(--border);
            transition: all 0.3s ease;
        }
        .channel-group.offline { opacity: 0.4; pointer-events: none; }
        .channel-group.offline .switch { pointer-events: all; }

        #admin-panel { display: none; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }

        .security-card {
            background: rgba(239, 68, 68, 0.1);
            border: 2px solid var(--danger);
            border-radius: 20px;
            padding: 24px;
            margin: 10px 0;
            animation: pulse-border 2s infinite;
        }
        @keyframes pulse-border {
            0% { border-color: rgba(239, 68, 68, 0.4); }
            50% { border-color: rgba(239, 68, 68, 1); }
            100% { border-color: rgba(239, 68, 68, 0.4); }
        }

        /* Toast Notifications */
        #toast-container {
            position: fixed;
            top: 24px;
            right: 24px;
            z-index: 100000;
            display: flex;
            flex-direction: column;
            gap: 12px;
            pointer-events: none;
        }
        .toast {
            min-width: 300px;
            padding: 16px 24px;
            border-radius: 16px;
            background: var(--surface);
            backdrop-filter: var(--glass);
            border: 1px solid var(--border);
            color: var(--text-main);
            box-shadow: var(--card-shadow);
            display: flex;
            align-items: center;
            gap: 12px;
            pointer-events: auto;
            animation: toastEnter 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            font-weight: 600;
            font-size: 0.9rem;
        }
        @keyframes toastEnter {
            from { opacity: 0; transform: translateX(20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        .toast.exit {
            animation: toastExit 0.4s forwards;
        }
        @keyframes toastExit {
            to { opacity: 0; transform: translateX(20px); }
        }
        .toast-success { border-left: 4px solid var(--secondary); }
        .toast-error { border-left: 4px solid var(--danger); }
        .toast-info { border-left: 4px solid var(--primary); }
    </style>
</head>
<body>
    <div id="toast-container"></div>

    <!-- Auth Layer -->
    <div id="auth-overlay" class="auth-portal">
        <div class="auth-card" id="login-view">
            <div style="font-size: 4rem; margin-bottom: 32px;">🦞</div>
            <h1 style="margin-bottom: 8px; font-weight: 800;">YOUCLAW</h1>
            <p style="color: var(--text-dim); margin-bottom: 32px;">Platform Control Center</p>
            <div class="input-group"><span class="input-label">Username</span><input type="text" id="auth-username" class="text-input"></div>
            <div class="input-group"><span class="input-label">Password</span><input type="password" id="auth-password" class="text-input"></div>
            <button class="btn btn-primary" style="width: 100%;" onclick="doLogin()">Enter System 🔐</button>
            <button class="btn btn-outline" style="width: 100%; margin-top: 16px;" onclick="showAuthView('register-view')">Register Agent</button>
        </div>
        <div class="auth-card" id="register-view" style="display: none;">
            <h1 style="margin-bottom: 8px; font-weight: 800;">New Profile</h1>
            <p style="color: var(--text-dim); margin-bottom: 32px;">Initialize Neural Protocol</p>
            <div class="input-group"><span class="input-label">Username</span><input type="text" id="reg-username" class="text-input"></div>
            <div class="input-group"><span class="input-label">Password</span><input type="password" id="reg-password" class="text-input"></div>
            <button class="btn btn-primary" style="width: 100%;" onclick="doRegister()">Initialize Account 🚀</button>
            <button class="btn btn-outline" style="width: 100%; margin-top: 16px;" onclick="showAuthView('login-view')">Back to Auth</button>
        </div>
        <div class="auth-card" id="link-view" style="display: none;">
            <h1 style="margin-bottom: 8px; font-weight: 800;">Neural Link</h1>
            <p style="color: var(--text-dim); margin-bottom: 32px;">Sync platform identity</p>
            <div class="input-group"><span class="input-label">Architecture</span><select id="link-platform" class="text-input"><option value="telegram">Telegram</option><option value="discord">Discord</option></select></div>
            <div class="input-group"><span class="input-label">Protocol ID</span><input type="text" id="link-id" class="text-input" placeholder="Platform user ID"></div>
            <button class="btn btn-primary" style="width: 100%;" onclick="doLink()">Secure Link 🔗</button>
        </div>
    </div>

    <!-- Sidebar Navigation -->
    <nav class="sidebar" id="app-sidebar" style="display: none;">
        <div>
            <div class="sidebar-logo">🦞 YOUCLAW <span style="font-size: 0.6rem; color: var(--primary);">V4.9.5</span></div>
            <div class="nav-list">
                <div class="nav-item active" id="nav-dash" onclick="switchView('dashboard')"><i>📊</i> Control Center</div>
                <div class="nav-item" id="nav-chat" onclick="switchView('chat')"><i>💬</i> Neural Terminal</div>
            </div>
        </div>
        <div style="margin-top: auto;">
            <div style="font-size: 0.7rem; color: var(--text-dim); font-weight: 800; text-transform: uppercase;">Operator</div>
            <div id="display-user" style="font-weight: 800; color: var(--primary); margin-top: 4px;">...</div>
            <button class="btn btn-outline" style="margin-top: 20px; width: 100%; padding: 12px;" onclick="doLogout()">Sign Out</button>
        </div>
    </nav>

    <!-- Main Stage -->
    <main class="main-stage">
        <div class="container" id="main-container">
            <div class="header-bar">
                <button class="theme-toggle" id="theme-btn" onclick="toggleTheme()">🌓</button>
            </div>

            <!-- View 1: Control Center Dashboard -->
            <div id="dashboard-view">
                <div class="dashboard-grid">
                    <div class="card" style="grid-column: span 12; border-color: var(--danger); display: none;" id="link-warning">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div><h3 style="color: var(--danger); font-weight: 800;">⚠️ Connectivity Restricted</h3><p style="color: var(--text-dim);">Identity link required for full mission capability.</p></div>
                            <button class="btn btn-primary" style="width: auto;" onclick="showAuthView('link-view')">Sync Identity</button>
                        </div>
                    </div>

                    <div class="card" style="grid-column: span 12;">
                        <div class="card-title">📊 Intelligence Summary</div>
                        <div class="stat-grid">
                            <div class="stat-item"><div class="input-label">Neural States</div><div class="stat-val" id="stat-messages">0</div></div>
                            <div class="stat-item"><div class="input-label">Connectivity</div><div class="stat-val" style="color: var(--secondary);">OPTIMAL</div></div>
                            <div class="stat-item"><div class="input-label">Active Engine</div><div class="stat-val" id="stat-model" style="font-size: 1rem; color: var(--primary);">...</div></div>
                        </div>
                    </div>

                    <div class="card" style="grid-column: span 6;">
                        <div class="card-title">🧠 Neural Core Configuration</div>
                        <div class="input-group">
                            <span class="input-label">Ollama Host URL</span>
                            <input type="text" id="vault-ollama" class="text-input" placeholder="http://localhost:11434">
                        </div>
                         <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: -10px; margin-bottom: 12px;">Changing this will instantly verify connectivity.</div>
                         <button class="btn btn-primary" onclick="saveSecrets(this)">Connect Core 🔌</button>
                    </div>

                    <div class="card" style="grid-column: span 6;">
                        <div class="card-title">🌐 Platform Connectivity</div>
                        <div style="display: flex; flex-direction: column; gap: 24px;">
                            <div class="channel-group">
                                <div class="toggle-row" style="padding: 0; margin-bottom: 12px;">
                                    <div><span style="font-weight: 700;">Telegram Protocol</span><div style="font-size: 0.8rem; color: var(--text-dim);">Active relay to global network</div></div>
                                    <label class="switch"><input type="checkbox" id="toggle-tg" onchange="toggleChannel('telegram', this)"><span class="slider"></span></label>
                                </div>
                                <div class="input-group" style="margin: 0; position: relative;">
                                    <input type="password" id="vault-tg" class="text-input" placeholder="Telegram Token" style="padding-right: 50px;">
                                    <button class="eye-btn" onclick="toggleSecret('vault-tg')">👁️</button>
                                </div>
                            </div>

                            <div class="channel-group">
                                <div class="toggle-row" style="padding: 0; margin-bottom: 12px;">
                                    <div><span style="font-weight: 700;">Discord Architecture</span><div style="font-size: 0.8rem; color: var(--text-dim);">Secure tunnel to Discord guild</div></div>
                                    <label class="switch"><input type="checkbox" id="toggle-dc" onchange="toggleChannel('discord', this)"><span class="slider"></span></label>
                                </div>
                                <div class="input-group" style="margin: 0; position: relative;">
                                    <input type="password" id="vault-dc" class="text-input" placeholder="Discord Token" style="padding-right: 50px;">
                                    <button class="eye-btn" onclick="toggleSecret('vault-dc')">👁️</button>
                                </div>
                            </div>

                            <div class="channel-group">
                                <div style="margin-bottom: 12px;">
                                    <span style="font-weight: 700;">Neural Search Node</span>
                                    <div style="font-size: 0.8rem; color: var(--text-dim);">Deep pulse data source</div>
                                </div>
                                <div class="input-group" style="margin: 0;">
                                    <input type="text" id="vault-search" class="text-input" placeholder="http://ip:port/search">
                                </div>
                            </div>

                            <div class="channel-group">
                                <div class="toggle-row" style="padding: 0; margin-bottom: 12px;">
                                    <div><span style="font-weight: 700;">Email Node Protocol</span><div style="font-size: 0.8rem; color: var(--text-dim);">Neural link to IMAP/SMTP</div></div>
                                    <label class="switch"><input type="checkbox" id="toggle-email" onchange="toggleChannel('email', this)"><span class="slider"></span></label>
                                </div>
                                <div style="display: grid; grid-template-columns: 1fr 80px; gap: 8px; margin-bottom: 8px;">
                                    <input type="text" id="vault-imap-host" class="text-input" placeholder="IMAP Host">
                                    <input type="number" id="vault-imap-port" class="text-input" placeholder="Port" value="993">
                                </div>
                                <div style="display: grid; grid-template-columns: 1fr 80px; gap: 8px; margin-bottom: 8px;">
                                    <input type="text" id="vault-smtp-host" class="text-input" placeholder="SMTP Host">
                                    <input type="number" id="vault-smtp-port" class="text-input" placeholder="Port" value="587">
                                </div>
                                <div class="input-group" style="margin: 0; margin-bottom: 8px;">
                                    <input type="text" id="vault-email-user" class="text-input" placeholder="Email User">
                                </div>
                                <div class="input-group" style="margin: 0; position: relative;">
                                    <input type="password" id="vault-email-pass" class="text-input" placeholder="Email Password" style="padding-right: 50px;">
                                    <button class="eye-btn" onclick="toggleSecret('vault-email-pass')">👁️</button>
                                </div>
                            </div>

                            <button class="btn btn-primary" style="margin-top: 8px;" onclick="saveSecrets(this)">Secure Vault 🔐</button>
                        </div>
                    </div>

                    <div class="card" style="grid-column: span 6;">
                        <div class="card-title">⚡ Automate Mission (Cron Job)</div>
                        <div class="input-group">
                            <span class="input-label">Briefing Protocol</span>
                            <input type="text" id="cron-prompt" class="text-input" placeholder="e.g. Give me a summary of today's tech news">
                        </div>
                        <div style="display: flex; gap: 16px;">
                            <div class="input-group" style="flex: 1;">
                                <span class="input-label">Frequency (Min)</span>
                                <input type="number" id="cron-freq" class="text-input" value="60">
                            </div>
                            <div class="input-group" style="flex: 1;">
                                <span class="input-label">Target Channel</span>
                                <select id="cron-channel" class="text-input">
                                    <option value="telegram" id="cron-opt-tg">Telegram Bot</option>
                                    <option value="discord" id="cron-opt-dc">Discord Bot</option>
                                </select>
                            </div>
                        </div>
                        <button class="btn btn-primary" style="width: 100%;" onclick="scheduleCron()">Activate Cron Job 🚀</button>
                    </div>

                    <div class="card" style="grid-column: span 12;">
                        <div class="card-title">⏰ Active Cron Jobs</div>
                        <div id="jobs-list" class="dashboard-grid" style="grid-template-columns: repeat(3, 1fr); gap: 24px;"></div>
                    </div>

                    <div class="card" style="grid-column: span 12;">
                        <div class="card-title">💬 Active Conversations</div>
                        <div id="conversations-list" class="dashboard-grid" style="grid-template-columns: repeat(4, 1fr); gap: 24px;"></div>
                    </div>
                </div>

                <div id="admin-panel" style="margin-top: 32px;">
                    <h2 style="font-size: 0.8rem; letter-spacing: 3px; color: var(--text-dim); margin-bottom: 24px;">ROOT PROTOCOLS</h2>
                    <div class="dashboard-grid">
                        <div class="card" style="grid-column: span 12;">
                            <div class="card-title">⚙️ Core Migration</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: end;">
                                <div class="input-group" style="margin: 0;">
                                    <span class="input-label">Standard Engines</span>
                                    <select id="model-list" class="text-input"></select>
                                </div>
                                <div style="display: flex; gap: 16px;">
                                    <button class="btn btn-outline" style="flex: 1;" onclick="switchModel(this)">Migrate Core</button>
                                    <button class="btn btn-outline" style="flex: 1; color: var(--danger); border-color: var(--danger);" onclick="clearMemory()">Purge States</button>
                                </div>
                            </div>
                        </div>
                        <div class="card" style="grid-column: span 12; margin-top: 24px;">
                            <div class="card-title">🧬 Neural Soul Architecture</div>
                            <div style="display: grid; grid-template-columns: 1fr auto; gap: 24px; align-items: start;">
                                <div class="input-group" style="margin: 0;">
                                    <span class="input-label">Active Personality</span>
                                    <div id="personality-container" style="display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px;"></div>
                                </div>
                                <div class="stat-item" style="border: 1px solid var(--border); background: rgba(0,0,0,0.1); padding: 16px 24px;">
                                    <div class="input-label">Current Soul</div>
                                    <div class="stat-val" id="current-soul-display" style="font-size: 1.1rem; color: var(--primary);">Loading...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            </div>

            <!-- View 2: Neural Terminal Chatbox -->
            <div id="neural-terminal-view">
                <div class="chat-layout">
                    <div class="chat-main">
                        <div id="chat-messages"></div>
                        <div class="chat-input-area">
                            <input type="text" id="chat-input" class="chat-field" placeholder="Whisper your intent..." onkeydown="if(event.key==='Enter') sendChat()">
                            <button id="send-btn" class="send-btn" onclick="sendChat()">🚀</button>
                        </div>
                    </div>
                    
                    <div class="chat-sidebar">
                        <div class="card" style="height: 100%;">
                            <div class="card-title">✨ Active Neural Soul</div>
                            <div id="current-soul-display-chat" style="font-size: 1.5rem; font-weight: 800; color: var(--accent); margin-bottom: 24px;">Syncing...</div>
                            
                            <div class="input-label">Shift Frequency</div>
                            <div id="personality-container-chat" style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px;"></div>
                            
                            <div style="margin-top: 40px;">
                                <div class="input-label">System Statistics</div>
                                <div style="display: flex; flex-direction: column; gap: 16px; margin-top: 12px;">
                                    <div style="display: flex; justify-content: space-between;">
                                        <span style="color: var(--text-dim);">Neural Core</span>
                                        <span id="stat-model-chat" style="font-weight: 800;">Loading...</span>
                                    </div>
                                    <div style="display: flex; justify-content: space-between;">
                                        <span style="color: var(--text-dim);">Synapses Fried</span>
                                        <span id="stat-messages-chat" style="font-weight: 800;">0</span>
                                    </div>
                                </div>
                            </div>

                            <div style="margin-top: 40px; padding: 20px; background: rgba(0,0,0,0.1); border-radius: 20px; border: 1px solid var(--border);">
                                <div class="input-label" style="margin-bottom: 12px;">Neural Activity</div>
                                <div id="search-status" style="font-size: 0.8rem; color: var(--text-dim);">
                                    <span class="pulse" style="background: var(--secondary);"></span> Listening for queries...
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
    </main>

    <script>
        let session_user = null;
        let state_hash = { jobs: '', stats: '' };

        function toggleTheme() {
            const html = document.documentElement;
            const newTheme = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('yc_theme', newTheme);
            document.getElementById('theme-btn').innerText = newTheme === 'dark' ? '🌓' : '☀️';
        }

        function toggleSecret(id) {
            const el = document.getElementById(id);
            el.type = el.type === 'password' ? 'text' : 'password';
        }

        let webMode = false;
        function toggleWebMode() {
            webMode = !webMode;
            document.getElementById('web-search-toggle').classList.toggle('active', webMode);
        }

        function switchView(view) {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.getElementById('dashboard-view').style.display = 'none';
            document.getElementById('neural-terminal-view').style.display = 'none';
            
            if(view === 'dashboard') {
                document.getElementById('nav-dash').classList.add('active');
                document.getElementById('dashboard-view').style.display = 'block';
            } else {
                document.getElementById('nav-chat').classList.add('active');
                document.getElementById('neural-terminal-view').style.display = 'block';
                document.getElementById('chat-input').focus();
            }
        }

        function showAuthView(id) {
            document.querySelectorAll('.auth-card').forEach(v => v.style.display = 'none');
            document.getElementById(id).style.display = 'block';
            document.getElementById('auth-overlay').style.display = 'flex';
        }

        async function doRegister() {
            const u = document.getElementById('reg-username').value;
            const p = document.getElementById('reg-password').value;
            const res = await apiCall('/api/auth/register', 'POST', { username:u, password:p });
            if(res.success) { showToast("Protocol Initialized. Welcome to YouClaw.", "success"); showAuthView('login-view'); }
            else showToast("Protocol Denied: " + res.error, "error");
        }

        async function doLogin() {
            const u = document.getElementById('auth-username').value;
            const p = document.getElementById('auth-password').value;
            const res = await apiCall('/api/auth/login', 'POST', { username:u, password:p });
            if(res.success && res.user.token) {
                session_user = u;
                localStorage.setItem('yc_session_user', u);
                localStorage.setItem('yc_session_token', res.user.token);
                initDashboard();
                showToast("Neural sync established.", "success");
            } else showToast("Neural auth failed.", "error");
        }

        async function doLink() {
            const p = document.getElementById('link-platform').value;
            const id = document.getElementById('link-id').value;
            const res = await apiCall('/api/auth/link', 'POST', { platform:p, user_id:id });
            if(res.success) { showToast("Identity Synced.", "success"); location.reload(); }
            else showToast("Link Fault.", "error");
        }

        function doLogout() { 
            localStorage.removeItem('yc_session_user'); 
            localStorage.removeItem('yc_session_token');
            location.reload(); 
        }

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            const target = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', target);
            localStorage.setItem('yc_theme', target);
            document.getElementById('theme-btn').innerText = target === 'dark' ? '🌓' : '☀️';
        }

        async function apiCall(url, method = 'GET', body = null) {
            const token = localStorage.getItem('yc_session_token');
            const h = { 
                'X-Session-User': session_user, 
                'X-Session-Token': token,
                'Content-Type': 'application/json' 
            };
            const options = { method, headers: h };
            if (body) options.body = JSON.stringify(body);
            const res = await fetch(url, options);
            const data = await res.json();
            return data;
        }

        function showToast(message, type = 'info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
            toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.classList.add('exit');
                setTimeout(() => toast.remove(), 400);
            }, 4000);
        }

        async function initDashboard() {
            session_user = localStorage.getItem('yc_session_user');
            if(!session_user) return showAuthView('login-view');
            
            const savedTheme = localStorage.getItem('yc_theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            document.getElementById('theme-btn').innerText = savedTheme === 'dark' ? '🌓' : '☀️';

            document.getElementById('auth-overlay').style.display = 'none';
            document.getElementById('app-sidebar').style.display = 'flex';
            document.getElementById('main-container').classList.add('active');
            document.getElementById('display-user').innerText = session_user;

            updateDashboard();
            setInterval(updateDashboard, 5000);
        }

        async function updateDashboard() {
            const stats = await apiCall('/api/stats');
            if(!stats || stats.error) return;

            document.getElementById('link-warning').style.display = stats.is_linked ? 'none' : 'block';
            document.getElementById('stat-messages').innerText = stats.user_messages;
            document.getElementById('stat-model').innerText = stats.model;
            
            const msgChat = document.getElementById('stat-messages-chat');
            const modelChat = document.getElementById('stat-model-chat');
            if(msgChat) msgChat.innerText = stats.user_messages;
            if(modelChat) modelChat.innerText = stats.model;

            document.getElementById('toggle-tg').checked = stats.telegram_enabled;
            document.getElementById('toggle-dc').checked = stats.discord_enabled;
            
            // Sync Cron Channel Detection
            const cronTg = document.getElementById('cron-opt-tg');
            const cronDc = document.getElementById('cron-opt-dc');
            cronTg.disabled = !stats.telegram_enabled;
            cronDc.disabled = !stats.discord_enabled;
            cronTg.innerText = stats.telegram_enabled ? "Telegram Bot" : "Telegram (Offline)";
            cronDc.innerText = stats.discord_enabled ? "Discord Bot" : "Discord (Offline)";

            // Update Channel Group States
            document.getElementById('toggle-tg').closest('.channel-group').classList.toggle('offline', !stats.telegram_enabled);
            document.getElementById('toggle-dc').closest('.channel-group').classList.toggle('offline', !stats.discord_enabled);
            
            if(stats.is_admin) {
                document.getElementById('admin-panel').style.display = 'block';
                const ms = document.getElementById('model-list');
                if(ms.options.length === 0 && stats.available_models) {
                    stats.available_models.forEach(m => {
                        const o = document.createElement('option'); o.value = o.innerText = m;
                        if(m === stats.model) o.selected = true;
                        ms.appendChild(o);
                    });
                }
                if(!window.vaultLoaded) { loadVault(); window.vaultLoaded = true; }
                if(!window.personalitiesLoaded) loadPersonalities();
            }

            const jobs = await apiCall('/api/jobs');
            if(jobs && !jobs.error && JSON.stringify(jobs.jobs) !== state_hash.jobs) {
                document.getElementById('jobs-list').innerHTML = jobs.jobs.map(j => `
                    <div class="item-card">
                        <div style="font-weight: 800; font-size: 0.9rem;">#${j.id}</div>
                        <div style="font-size: 0.8rem; color: var(--text-dim); margin: 8px 0;">${j.prompt.substring(0,60)}...</div>
                        <button onclick="deleteJob('${j.id}')" style="background:var(--danger); border:none; color:white; padding:6px 12px; border-radius:8px; font-weight:800; cursor:pointer; font-size:0.7rem;">ABORT</button>
                    </div>
                `).join('') || '<div style="grid-column: span 3; color: var(--text-dim); text-align:center;">No active heartbeats</div>';
                state_hash.jobs = JSON.stringify(jobs.jobs);
            }

            const convs = await apiCall('/api/conversations');
            if(convs && !convs.error) {
                document.getElementById('conversations-list').innerHTML = convs.conversations.map(c => `
                    <div class="item-card">
                        <div style="font-size: 0.85rem; font-weight: 800;">Thread: ${(c.channel_id || 'Direct').substring(0,8)}...</div>
                        <div style="font-size: 0.75rem; color: var(--text-dim);">${c.message_count} states synced</div>
                    </div>
                `).join('');
            }
            
            // Sync Mission Control if active
            const missionView = document.getElementById('mission-view');
            if(missionView && missionView.style.display === 'block') {
                updateMissionControl();
            }
        }

        async function toggleChannel(channel, el) {
            const res = await apiCall('/api/system/toggle_channel', 'POST', { channel: channel, enabled: el.checked });
            if(!res.success) { showToast("Toggle Failure.", "error"); el.checked = !el.checked; }
        }

        async function scheduleCron() {
            const prompt = document.getElementById('cron-prompt').value;
            const freq = document.getElementById('cron-freq').value;
            const sel = document.getElementById('cron-channel');
            const channel = sel.value;
            if(!prompt) return showToast("Briefing required.", "error");
            if(sel.options[sel.selectedIndex].disabled) return showToast("Selected channel is offline. Activate it first.", "error");
            
            const res = await apiCall('/api/jobs/schedule', 'POST', { 
                prompt: prompt, 
                frequency: freq,
                channel: channel 
            });
            if(res.success) {
                showToast("Cron Job Activated! 🚀", "success");
                document.getElementById('cron-prompt').value = '';
                updateDashboard();
            } else showToast("Activation Fault: " + res.error, "error");
        }

        async function sendChat() {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('send-btn');
            const msg = input.value.trim();
            if(!msg || btn.disabled) return;
            
            const box = document.getElementById('chat-messages');
            box.innerHTML += `<div class="msg msg-user">${msg}</div>`;
            input.value = '';
            input.disabled = btn.disabled = true;
            
            const indicator = document.createElement('div');
            indicator.className = 'typing-indicator';
            indicator.innerHTML = '<div class="typing-label">Thinking</div><div class="dot"></div><div class="dot"></div><div class="dot"></div>';
            box.appendChild(indicator);
            box.scrollTop = box.scrollHeight;
            
            const searchStatus = document.getElementById('search-status');
            if(searchStatus) searchStatus.innerHTML = '<span class="pulse"></span> Synapsing Neural Streams...';

            try {
                const url = `/api/chat/stream?user=${encodeURIComponent(session_user)}&message=${encodeURIComponent(msg)}`;
                const token = localStorage.getItem('yc_session_token');
                const response = await fetch(url, {
                    headers: { 'X-Session-User': session_user, 'X-Session-Token': token }
                });
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                const aiMsg = document.createElement('div');
                aiMsg.className = 'msg msg-ai';
                let fullAiResponse = '';
                
                let firstChunk = true;
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    if (firstChunk) {
                        indicator.remove();
                        box.appendChild(aiMsg);
                        firstChunk = false;
                    }
                    
                    const chunk = decoder.decode(value, { stream: true });
                    fullAiResponse += chunk;
                    
                    if (fullAiResponse.includes("[SECURITY_INTERCEPT]")) {
                        // Handle Iron Dome UI
                        const parts = fullAiResponse.split(' ');
                        const reqId = parts[1].split(':')[1];
                        const cmd = parts[2].split(':')[1];
                        
                        aiMsg.className = 'msg msg-ai security-card';
                        aiMsg.innerHTML = `
                            <div style="font-weight: 800; color: var(--danger); margin-bottom: 10px;">🛡️ IRON DOME INTERCEPT</div>
                            <p style="margin-bottom: 16px;">I need your permission to run: <code style="background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 6px;">${cmd}</code></p>
                            <div style="display: flex; gap: 10px;">
                                <button class="btn btn-primary" style="flex: 1; background: var(--secondary);" onclick="approveSecurity('${reqId}', this)">✅ Approve</button>
                                <button class="btn btn-outline" style="flex: 1;" onclick="denySecurity('${reqId}', this)">❌ Deny</button>
                            </div>
                        `;
                        // Stop streaming here
                        break;
                    } else {
                        aiMsg.innerHTML = marked.parse(fullAiResponse);
                    }
                    box.scrollTop = box.scrollHeight;
                }
            } catch (err) {
                if(indicator.parentNode) indicator.remove();
                box.innerHTML += `<div class="msg msg-ai" style="color:var(--danger)">Protocol Fault</div>`;
            } finally {
                input.disabled = btn.disabled = false;
                input.focus();
                box.scrollTop = box.scrollHeight;
                if(searchStatus) searchStatus.innerHTML = '<span class="pulse" style="background: var(--secondary);"></span> Listening for queries...';
                updateDashboard();
            }
        }

        async function deleteJob(id) {
            if(!confirm("Terminate this mission?")) return;
            const res = await apiCall('/api/jobs/delete', 'POST', { job_id: id });
            if(res.success) updateDashboard();
        }

        async function loadVault() {
            const data = await apiCall('/api/system/env');
            if(data && !data.error) {
                document.getElementById('vault-tg').value = data.telegram_token || "";
                document.getElementById('vault-dc').value = data.discord_token || "";
                document.getElementById('vault-search').value = data.search_url || "";
                document.getElementById('vault-ollama').value = data.ollama_url || "";
                
                if(data.email) {
                    document.getElementById('toggle-email').checked = data.email.enabled;
                    document.getElementById('vault-imap-host').value = data.email.imap_host || "";
                    document.getElementById('vault-imap-port').value = data.email.imap_port || 993;
                    document.getElementById('vault-smtp-host').value = data.email.smtp_host || "";
                    document.getElementById('vault-smtp-port').value = data.email.smtp_port || 587;
                    document.getElementById('vault-email-user').value = data.email.user || "";
                }
            }
        }

        async function loadPersonalities() {
            const data = await apiCall('/api/system/personality');
            if(!data || data.error) return;
            
            const container = document.getElementById('personality-container');
            const containerChat = document.getElementById('personality-container-chat');
            if(container) container.innerHTML = '';
            if(containerChat) containerChat.innerHTML = '';
            
            for(const [id, p] of Object.entries(data.personalities)) {
                const pill = document.createElement('div');
                pill.className = `p-pill ${id === data.active ? 'active' : ''}`;
                pill.innerText = p.name;
                pill.title = p.description;
                pill.onclick = () => switchPersonality(id);
                
                if(container) container.appendChild(pill);
                
                const pillChat = pill.cloneNode(true);
                pillChat.onclick = () => switchPersonality(id);
                if(containerChat) containerChat.appendChild(pillChat);
            }
            const soulName = data.personalities[data.active].name;
            const soulDisp = document.getElementById('current-soul-display');
            const soulChat = document.getElementById('current-soul-display-chat');
            if(soulDisp) soulDisp.innerText = soulName;
            if(soulChat) soulChat.innerText = soulName;
            
            window.personalitiesLoaded = true;
        }

        async function switchPersonality(id) {
            const res = await apiCall('/api/system/personality', 'POST', { personality: id });
            if(res.success) {
                loadPersonalities();
                updateDashboard();
            } else showToast("Personality shift failed.", "error");
        }

        async function saveSecrets(btn) {
            btn.innerText = "Syncing..."; btn.disabled = true;
            const res = await apiCall('/api/system/secrets', 'POST', {
                telegram_token: document.getElementById('vault-tg').value,
                discord_token: document.getElementById('vault-dc').value,
                search_url: document.getElementById('vault-search').value,
                ollama_url: document.getElementById('vault-ollama').value,
                email: {
                    imap_host: document.getElementById('vault-imap-host').value,
                    imap_port: parseInt(document.getElementById('vault-imap-port').value),
                    smtp_host: document.getElementById('vault-smtp-host').value,
                    smtp_port: parseInt(document.getElementById('vault-smtp-port').value),
                    user: document.getElementById('vault-email-user').value,
                    password: document.getElementById('vault-email-pass').value
                }
            });
            if(res.success) {
                let msg = "Vault updated.";
                if(res.ollama_status !== "unchanged") {
                    msg += " AI Core Status: " + res.ollama_status.toUpperCase();
                }
                showToast(msg, "success");
                updateDashboard();
            }
            btn.innerText = "Apply Changes"; btn.disabled = false;
        }

        async function switchModel(btn) {
            btn.innerText = "Migrating..."; btn.disabled = true;
            const res = await apiCall('/api/model/switch', 'POST', { model: document.getElementById('model-list').value });
            if(res.success) showToast("Neural engine migrated.", "success");
            btn.innerText = "Migrate Core"; btn.disabled = false;
        }

        async function clearMemory() {
            if(!confirm("Purge neural state? Permanent action.")) return;
            await apiCall('/api/memory/clear', 'POST');
            updateDashboard();
        }

        async function approveSecurity(reqId, btn) {
            const card = btn.closest('.security-card');
            card.innerHTML = `<div style="text-align: center; padding: 10px;"><span class="pulse"></span> Executing command...</div>`;
            
            try {
                const res = await apiCall('/api/security/approve', 'POST', { action: 'approve', request_id: reqId });
                if (res.success) {
                    card.className = 'msg msg-ai';
                    card.style.animation = 'none';
                    card.style.borderColor = 'var(--border)';
                    card.style.background = 'var(--bubble-ai)';
                    card.innerHTML = `<div style="font-weight: 800; margin-bottom: 8px;">✅ Output:</div><pre style="white-space: pre-wrap; font-size: 0.85rem; background: rgba(0,0,0,0.2); padding: 15px; border-radius: 12px;">${res.result}</pre>`;
                } else {
                    card.innerHTML = `<div style="color: var(--danger);">Error: ${res.error || 'Execution failed'}</div>`;
                }
            } catch (e) {
                card.innerHTML = `<div style="color: var(--danger);">Connection error</div>`;
            }
        }

        async function denySecurity(reqId, btn) {
            const card = btn.closest('.security-card');
            await apiCall('/api/security/approve', 'POST', { action: 'deny', request_id: reqId });
            card.innerHTML = `<div style="color: var(--danger); font-weight: 700;">❌ Action Denied</div>`;
            setTimeout(() => card.remove(), 2000);
        }

        initDashboard();
        console.log("🦞 YouClaw Dashboard v4.9.5 loaded successfully");
    </script>
</body>
</html>
"""


async def run_dashboard(bot_instance=None, port=8080):
    """Run the dashboard web server"""
    app = web.Application()
    app['bot'] = bot_instance
    app.router.add_routes(routes)
    
    await memory_manager.initialize()
    await config.refresh_from_db() # Load saved settings (Ollama URL etc)
    await ollama_client.initialize()
    
    print(f"🦞 YouClaw Dashboard starting on http://0.0.0.0:{port}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    try: await asyncio.Event().wait()
    finally: await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run_dashboard())

