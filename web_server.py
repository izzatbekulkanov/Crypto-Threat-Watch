"""Telegram Mini App uchun web server + SSH tunnel (localhost.run)."""

import asyncio
import logging
import re
import hmac
import hashlib
import urllib.parse
import json
from pathlib import Path
from typing import Optional

from aiohttp import web

from config import BOT_TOKEN
from database import get_stats, get_all_users, get_recent_audits, is_admin

logger: logging.Logger = logging.getLogger(__name__)

WEBAPP_DIR: Path = Path(__file__).resolve().parent / "webapp"
WEB_PORT: int = 8443

# Global tunnel URL
_tunnel_url: str = ""
_tunnel_process: asyncio.subprocess.Process | None = None


def get_tunnel_url() -> str:
    """Hozirgi tunnel URL ni qaytarish."""
    return _tunnel_url


async def handle_index(request: web.Request) -> web.Response:
    """Mini App asosiy sahifasi."""
    html_path = WEBAPP_DIR / "index.html"
    html_content = html_path.read_text(encoding="utf-8")
    return web.Response(text=html_content, content_type="text/html", charset="utf-8")


async def handle_stats(request: web.Request) -> web.Response:
    """API: Umumiy statistika."""
    stats = get_stats()
    return web.json_response(stats)


async def handle_users(request: web.Request) -> web.Response:
    """API: Foydalanuvchilar ro'yxati."""
    users = get_all_users()
    return web.json_response(users)


async def handle_audits(request: web.Request) -> web.Response:
    """API: Oxirgi auditlar."""
    audits = get_recent_audits(50)
    return web.json_response(audits)


async def handle_action(request: web.Request) -> web.Response:
    """API: Foydalanuvchi amallarini bajarish."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    action = data.get("action")
    try:
        target_user = int(data.get("user_id"))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid user_id format"}, status=400)
    
    if not action or not target_user:
        return web.json_response({"error": "Missing parameters"}, status=400)
        
    try:
        from database import toggle_admin, update_alias, approve_user, delete_user
        
        if action == "toggle_admin":
            new_status = toggle_admin(target_user)
            return web.json_response({"success": True, "result": "admin_toggled", "is_admin": new_status})
        elif action == "edit_alias":
            new_alias = data.get("alias")
            if not new_alias:
                return web.json_response({"error": "Missing alias"}, status=400)
            update_alias(target_user, new_alias)
            return web.json_response({"success": True, "result": "alias_updated"})
        elif action == "approve":
            approve_user(target_user, True)
            return web.json_response({"success": True, "result": "user_approved"})
        elif action == "disapprove":
            approve_user(target_user, False)
            return web.json_response({"success": True, "result": "user_disapproved"})
        elif action == "delete_user":
            delete_user(target_user)
            return web.json_response({"success": True, "result": "user_deleted"})
        else:
            return web.json_response({"error": f"Unknown action: {action}"}, status=400)
    except Exception as e:
        logger.error(f"Error executing action {action} on user {target_user}: {e}")
        return web.json_response({"error": str(e)}, status=500)
async def broadcast_in_background(user_ids: list[int], text: str):
    """Barcha foydalanuvchilarga xabarni orqa fonda yuborish."""
    import aiohttp
    logger.info(f"Broadcasting message to {len(user_ids)} users in background...")
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        for uid in user_ids:
            payload = {
                "chat_id": uid,
                "text": text,
                "parse_mode": "HTML"
            }
            try:
                async with session.post(url, json=payload) as resp:
                    await resp.read()
            except Exception as e:
                logger.error(f"Broadcast error for user {uid}: {e}")
            await asyncio.sleep(0.05)
    logger.info("Broadcast task completed.")


async def handle_broadcast(request: web.Request) -> web.Response:
    """API: Barcha foydalanuvchilarga xabar yuborish."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    message_text = data.get("message", "").strip()
    if not message_text:
        return web.json_response({"error": "Message content cannot be empty"}, status=400)
        
    users = get_all_users()
    user_ids = [u["user_id"] for u in users]
    
    # Spawn background task to send messages
    asyncio.create_task(broadcast_in_background(user_ids, message_text))
    
    return web.json_response({
        "success": True, 
        "total_queued": len(user_ids)
    })


def verify_telegram_init_data(init_data: str) -> Optional[int]:
    """Verifies Telegram Web App initData and returns user ID if valid."""
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed:
            return None
        
        received_hash = parsed.pop("hash")
        
        # Sort and join
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        
        # Secret key is HMAC-SHA256 of bot token with constant string "WebAppData"
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == received_hash:
            user_data = json.loads(parsed.get("user", "{}"))
            return user_data.get("id")
    except Exception as e:
        logger.warning(f"Init data verification failed: {e}")
    return None


@web.middleware
async def admin_auth_middleware(request: web.Request, handler):
    """Middleware to restrict /api/ endpoints to Telegram Admins only."""
    if request.method == "OPTIONS":
        return web.Response(status=200)

    if request.path.startswith("/api/"):
        # 1. Telegram Init Data validation (preferred)
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        user_id = verify_telegram_init_data(init_data)
        
        # 2. Secure Token fallback (for external browsers)
        if not user_id:
            admin_id_str = request.headers.get("X-Admin-Id", "")
            admin_token = request.headers.get("X-Admin-Token", "")
            if admin_id_str and admin_token:
                try:
                    admin_id = int(admin_id_str)
                    expected_token = hmac.new(BOT_TOKEN.encode(), str(admin_id).encode(), hashlib.sha256).hexdigest()
                    if hmac.compare_digest(expected_token, admin_token):
                        user_id = admin_id
                except (ValueError, TypeError):
                    pass
        
        if not user_id or not is_admin(user_id):
            return web.json_response({"error": "Unauthorized. Admins only."}, status=403)
            
    return await handler(request)


def create_web_app() -> web.Application:
    """Web ilovasini yaratish."""
    app: web.Application = web.Application()

    # CORS va headers middleware
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "X-Telegram-Init-Data, Content-Type, Authorization"
        response.headers["Connection"] = "keep-alive"
        return response

    app.middlewares.append(cors_middleware)
    app.middlewares.append(admin_auth_middleware)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/users", handle_users)
    app.router.add_get("/api/audits", handle_audits)
    app.router.add_post("/api/action", handle_action)
    app.router.add_post("/api/broadcast", handle_broadcast)
    app.router.add_static("/static/", path=str(WEBAPP_DIR), name="static")
    return app


async def _consume_stream(reader) -> None:
    """Consumes lines from a reader stream in the background to prevent subprocess deadlock."""
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="ignore").strip()
            if decoded:
                logger.info(f"Tunnel log: {decoded}")
    except Exception as e:
        logger.warning(f"Error consuming stream: {e}")


async def _open_tunnel(port: int) -> str:
    """cloudflared orqali Cloudflare Tunnel ochish (bepul HTTPS).

    Returns:
        HTTPS public URL yoki bo'sh string.
    """
    global _tunnel_process

    try:
        _tunnel_process = await asyncio.create_subprocess_exec(
            "/usr/local/bin/cloudflared",
            "tunnel",
            "--config", "/dev/null",
            "--protocol", "http2",
            "--url", f"http://localhost:{port}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # URL ni stdout/stderr dan olish (max 20 soniya kutish)
        for _ in range(40):
            if _tunnel_process.stdout:
                try:
                    line = await asyncio.wait_for(
                        _tunnel_process.stdout.readline(), timeout=0.5
                    )
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        logger.info(f"Tunnel output: {decoded}")
                        # trycloudflare.com URL
                        url_match = re.search(r"(https://[^\s]+\.trycloudflare\.com)", decoded)
                        if url_match:
                            # Start background task to consume remaining stdout and prevent pipe buffer deadlock
                            asyncio.create_task(_consume_stream(_tunnel_process.stdout))
                            return url_match.group(1)
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(0.5)

    except FileNotFoundError:
        logger.error("cloudflared topilmadi. Tunnel ishlamaydi.")
    except Exception as e:
        logger.error(f"Tunnel xatolik: {e}")

    return ""


async def start_web_server(ngrok_token: str = "") -> web.AppRunner:
    """Web serverni ishga tushirish va tunnel ochish."""
    global _tunnel_url

    # Web server
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    logger.info(f"🌐 Web server: http://localhost:{WEB_PORT}")

    # Cloudflare Tunnel
    logger.info("🔗 Tunnel ochilmoqda (Cloudflare)...")
    _tunnel_url = await _open_tunnel(WEB_PORT)

    if _tunnel_url:
        logger.info(f"✅ Mini App URL: {_tunnel_url}")
    else:
        logger.warning("⚠️ Tunnel ochilmadi. /web ishlamaydi.")
        logger.warning("   SSH mavjudligini tekshiring.")

    return runner
