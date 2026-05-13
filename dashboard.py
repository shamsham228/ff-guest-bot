# dashboard.py
# Web dashboard — runs alongside the Telegram bot
# Access at: https://your-render-url.onrender.com

import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from stats_manager import load_stats, get_success_rate, get_today_count
from proxy_manager import proxy_manager
from api_creator import create_multiple_guests

load_dotenv()

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")

app = FastAPI(title="FF Guest Bot Dashboard", docs_url=None, redoc_url=None)

# Templates directory
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")


# ── Auth Helper ───────────────────────────────────────────────────

def check_auth(request: Request):
    """Simple password authentication via query param or header"""
    password = (
        request.query_params.get("password") or
        request.headers.get("x-password") or
        ""
    )
    if password != DASHBOARD_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Wrong password. Add ?password=yourpassword to URL"
        )
    return True


# ── Helper Functions ──────────────────────────────────────────────

def get_total_accounts() -> int:
    """Count total accounts in database"""
    try:
        with open("guests_converted.json", "r") as f:
            return len(json.load(f))
    except Exception:
        return 0


def get_recent_accounts(limit: int = 15) -> list[dict]:
    """Get most recent accounts"""
    try:
        stats = load_stats()
        return stats.get("recent_accounts", [])[:limit]
    except Exception:
        return []


def get_uptime() -> str:
    """Get bot uptime"""
    try:
        stats = load_stats()
        start = datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S")
        diff  = datetime.now() - start
        hours = int(diff.total_seconds() // 3600)
        mins  = int((diff.total_seconds() % 3600) // 60)
        return f"{hours}h {mins}m"
    except Exception:
        return "Unknown"


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root redirect to dashboard info"""
    return HTMLResponse("""
    <html>
    <body style="background:#111;color:#0f0;font-family:monospace;padding:40px">
        <h1>🔥 FF Guest Bot</h1>
        <p>Dashboard: <a href="/dashboard?password=admin123" style="color:#0f0">/dashboard?password=admin123</a></p>
        <p>API Stats: <a href="/api/stats?password=admin123" style="color:#0f0">/api/stats?password=admin123</a></p>
        <p>Health: <a href="/health" style="color:#0f0">/health</a></p>
    </body>
    </html>
    """)


@app.get("/health")
async def health():
    """Health check endpoint — UptimeRobot pings this"""
    return {
        "status":  "online",
        "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total":   get_total_accounts(),
        "uptime":  get_uptime()
    }


@app.get("/api/stats")
async def api_stats(auth=Depends(check_auth)):
    """API endpoint for stats"""
    stats        = load_stats()
    proxy_stats  = proxy_manager.get_stats()
    return {
        "bot_stats":    stats,
        "proxy_stats":  proxy_stats,
        "total_accounts": get_total_accounts(),
        "success_rate": get_success_rate(),
        "today_count":  get_today_count(),
        "uptime":       get_uptime()
    }


@app.get("/api/accounts")
async def api_accounts(auth=Depends(check_auth), limit: int = 20):
    """Get recent accounts via API"""
    try:
        with open("guests_converted.json", "r") as f:
            accounts = json.load(f)
        return {"accounts": accounts[-limit:], "total": len(accounts)}
    except Exception:
        return {"accounts": [], "total": 0}


@app.post("/api/create")
async def api_create(
    request: Request,
    count: int = 1,
    auth=Depends(check_auth)
):
    """Manually trigger account creation from dashboard"""
    count   = max(1, min(count, 5))
    results = await create_multiple_guests(count)
    success = [r for r in results if r.get("success")]
    return {
        "created": len(success),
        "failed":  len(results) - len(success),
        "accounts": success
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, auth=Depends(check_auth)):
    """Main dashboard page"""
    stats       = load_stats()
    proxy_stats = proxy_manager.get_stats()
    recent      = get_recent_accounts(15)
    total       = get_total_accounts()
    today       = get_today_count()
    rate        = get_success_rate()
    uptime      = get_uptime()

    return templates.TemplateResponse("index.html", {
        "request":      request,
        "stats":        stats,
        "proxy_stats":  proxy_stats,
        "recent":       recent,
        "total":        total,
        "today":        today,
        "success_rate": rate,
        "uptime":       uptime,
        "password":     DASHBOARD_PASSWORD,
    })