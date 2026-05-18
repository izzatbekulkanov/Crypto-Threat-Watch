"""Telegram Mini App uchun web server + SSH tunnel (localhost.run)."""

import asyncio
import logging
import re
from pathlib import Path

from aiohttp import web

from database import get_stats, get_all_users, get_recent_audits

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


def create_web_app() -> web.Application:
    """Web ilovasini yaratish."""
    app: web.Application = web.Application()

    # CORS va headers middleware
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Connection"] = "keep-alive"
        return response

    app.middlewares.append(cors_middleware)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/users", handle_users)
    app.router.add_get("/api/audits", handle_audits)
    app.router.add_static("/static/", path=str(WEBAPP_DIR), name="static")
    return app


async def _open_tunnel(port: int) -> str:
    """localhost.run orqali SSH tunnel ochish (bepul HTTPS).

    Hech narsa o'rnatish kerak emas — faqat SSH.

    Returns:
        HTTPS public URL yoki bo'sh string.
    """
    global _tunnel_process

    try:
        _tunnel_process = await asyncio.create_subprocess_exec(
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=60",
            "-R", f"80:localhost:{port}",
            "nokey@localhost.run",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # URL ni stdout dan olish (max 15 soniya kutish)
        for _ in range(30):
            if _tunnel_process.stdout:
                try:
                    line = await asyncio.wait_for(
                        _tunnel_process.stdout.readline(), timeout=0.5
                    )
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        logger.info(f"Tunnel output: {decoded}")
                        # URL ni topish
                        url_match = re.search(r"(https://[a-z0-9]+\.lhr\.life[^\s]*)", decoded)
                        if url_match:
                            return url_match.group(1)
                        url_match2 = re.search(r"(https://[^\s]+\.localhost\.run[^\s]*)", decoded)
                        if url_match2:
                            return url_match2.group(1)
                        # Umumiy HTTPS URL
                        url_match3 = re.search(r"(https://[^\s]+)", decoded)
                        if url_match3:
                            return url_match3.group(1)
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(0.5)

    except FileNotFoundError:
        logger.error("SSH topilmadi. localhost.run ishlamaydi.")
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

    # SSH tunnel (localhost.run)
    logger.info("🔗 Tunnel ochilmoqda (localhost.run)...")
    _tunnel_url = await _open_tunnel(WEB_PORT)

    if _tunnel_url:
        logger.info(f"✅ Mini App URL: {_tunnel_url}")
    else:
        logger.warning("⚠️ Tunnel ochilmadi. /web ishlamaydi.")
        logger.warning("   SSH mavjudligini tekshiring.")

    return runner
