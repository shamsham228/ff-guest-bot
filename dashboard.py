# dashboard.py — Fixed dashboard (no external template files needed)
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
from stats_manager import (
    load_stats, get_success_rate,
    get_today_count, get_total_accounts, get_uptime
)
from proxy_manager import proxy_manager

load_dotenv()

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")

app = FastAPI(title="FF Guest Bot", docs_url=None, redoc_url=None)


def _check_auth(request: Request) -> bool:
    pw = (
        request.query_params.get("password") or
        request.headers.get("x-password") or
        ""
    )
    return pw == DASHBOARD_PASSWORD


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content)


# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "online",
        "time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total":  get_total_accounts(),
        "uptime": get_uptime()
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return _html("""
<!DOCTYPE html>
<html>
<head><title>FF Guest Bot</title>
<style>
body{background:#111;color:#0f0;font-family:monospace;
     display:flex;align-items:center;justify-content:center;
     height:100vh;margin:0}
.box{text-align:center;padding:40px;border:1px solid #0f0;border-radius:10px}
a{color:#0f0}
h1{font-size:2.5rem;margin-bottom:20px}
p{margin:10px 0;color:#999}
</style>
</head>
<body>
<div class="box">
  <h1>🔥 FF Guest Bot</h1>
  <p>Bot is running 24/7</p>
  <p><a href="/health">→ Health Check</a></p>
  <p><a href="/dashboard?password=admin123">→ Dashboard</a></p>
  <p><a href="/api/stats?password=admin123">→ API Stats</a></p>
</div>
</body>
</html>
""")


@app.get("/api/stats")
async def api_stats(request: Request):
    if not _check_auth(request):
        raise HTTPException(401, "Wrong password. Add ?password=...")
    return {
        "bot_stats":       load_stats(),
        "proxy_stats":     proxy_manager.get_stats(),
        "total_accounts":  get_total_accounts(),
        "success_rate":    get_success_rate(),
        "today_count":     get_today_count(),
        "uptime":          get_uptime(),
    }


@app.get("/api/accounts")
async def api_accounts(request: Request, limit: int = 20):
    if not _check_auth(request):
        raise HTTPException(401, "Wrong password")
    try:
        with open("guests_converted.json") as f:
            accounts = json.load(f)
        return {"accounts": accounts[-limit:], "total": len(accounts)}
    except Exception:
        return {"accounts": [], "total": 0}


@app.post("/api/create")
async def api_create(request: Request, count: int = 1):
    if not _check_auth(request):
        raise HTTPException(401, "Wrong password")
    from api_creator import create_multiple_guests
    count   = max(1, min(count, 5))
    results = await create_multiple_guests(count)
    success = [r for r in results if r.get("success")]
    return {
        "created":  len(success),
        "failed":   len(results) - len(success),
        "accounts": success
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _check_auth(request):
        return _html("""
<!DOCTYPE html>
<html>
<head><title>Login</title>
<style>
body{background:#111;color:#0f0;font-family:monospace;
     display:flex;align-items:center;justify-content:center;height:100vh}
input{background:#222;color:#0f0;border:1px solid #0f0;
      padding:10px;font-size:16px;border-radius:5px;font-family:monospace}
button{background:#0f0;color:#000;border:none;padding:10px 20px;
       font-size:16px;border-radius:5px;cursor:pointer;font-weight:bold;margin-left:10px}
.box{text-align:center;padding:40px;border:1px solid #0f0;border-radius:10px}
</style>
</head>
<body>
<div class="box">
  <h2>🔐 Dashboard Login</h2>
  <form onsubmit="login(event)">
    <input type="password" id="pw" placeholder="Enter dashboard password">
    <button type="submit">Enter</button>
  </form>
</div>
<script>
function login(e){
  e.preventDefault();
  const pw = document.getElementById('pw').value;
  window.location.href = '/dashboard?password=' + encodeURIComponent(pw);
}
</script>
</body>
</html>
""")

    # Load all data
    stats       = load_stats()
    proxy_stats = proxy_manager.get_stats()
    total       = get_total_accounts()
    today       = get_today_count()
    rate        = get_success_rate()
    uptime      = get_uptime()
    recent      = stats.get("recent_accounts", [])[:15]
    password    = request.query_params.get("password", "")

    # Build recent accounts HTML
    recent_html = ""
    if recent:
        for acc in recent:
            tok = "✅" if acc.get("token") else "❌"
            recent_html += f"""
            <div style="display:flex;justify-content:space-between;
                        align-items:center;background:#0f172a;
                        border-radius:8px;padding:10px 15px;margin:6px 0">
              <div>
                <span style="color:#60a5fa;font-family:monospace">
                  UID: {acc.get('uid','?')}
                </span>
                <span style="color:#6b7280;font-size:12px;margin-left:15px">
                  {acc.get('time','')}
                </span>
              </div>
              <span style="font-size:13px">{tok} Token</span>
            </div>"""
    else:
        recent_html = (
            '<p style="color:#6b7280;text-align:center;padding:30px">'
            'No accounts created yet</p>'
        )

    # Build daily chart data
    daily = stats.get("daily_counts", {})
    labels = list(daily.keys())[-7:]
    values = [daily[k] for k in labels]
    labels_js = json.dumps(labels)
    values_js = json.dumps(values)

    proxy_mode = "Proxy Rotation" if proxy_stats["using_proxies"] else "Direct"
    proxy_color = "#22c55e" if proxy_stats["using_proxies"] else "#f59e0b"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FF Guest Bot Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <meta http-equiv="refresh" content="15">
  <style>
    body {{ background:#0f172a; color:#f1f5f9; font-family:system-ui,sans-serif }}
    .card {{ background:#1e293b; border:1px solid #334155; border-radius:12px }}
    .stat-num {{ font-size:2.5rem; font-weight:800; line-height:1 }}
    .badge {{ padding:4px 10px; border-radius:20px; font-size:12px; font-weight:600 }}
  </style>
</head>
<body class="min-h-screen p-4">
<div style="max-width:1100px;margin:0 auto">

  <!-- Header -->
  <div style="display:flex;justify-content:space-between;
              align-items:center;margin-bottom:30px;
              padding:20px;background:#1e293b;
              border-radius:12px;border:1px solid #334155">
    <div>
      <h1 style="font-size:1.8rem;font-weight:800;color:#22c55e;margin:0">
        🔥 FF Guest Bot Dashboard
      </h1>
      <p style="color:#94a3b8;margin:5px 0 0">
        Auto-refreshes every 15s &nbsp;|&nbsp; Uptime: {uptime}
      </p>
    </div>
    <div style="text-align:right">
      <div class="badge" style="background:#22c55e22;color:#22c55e">
        🟢 ONLINE
      </div>
    </div>
  </div>

  <!-- Stat Cards -->
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px">
    <div class="card" style="padding:24px;text-align:center">
      <div class="stat-num" style="color:#60a5fa">{total}</div>
      <div style="color:#94a3b8;margin-top:8px;font-size:14px">Total Accounts</div>
    </div>
    <div class="card" style="padding:24px;text-align:center">
      <div class="stat-num" style="color:#22c55e">{today}</div>
      <div style="color:#94a3b8;margin-top:8px;font-size:14px">Created Today</div>
    </div>
    <div class="card" style="padding:24px;text-align:center">
      <div class="stat-num" style="color:#f59e0b">{rate}%</div>
      <div style="color:#94a3b8;margin-top:8px;font-size:14px">Success Rate</div>
    </div>
    <div class="card" style="padding:24px;text-align:center">
      <div class="stat-num" style="color:#a78bfa">
        {proxy_stats['available_proxies']}
      </div>
      <div style="color:#94a3b8;margin-top:8px;font-size:14px">Active Proxies</div>
    </div>
  </div>

  <!-- Main Grid -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">

    <!-- Recent Accounts -->
    <div class="card" style="padding:24px">
      <h2 style="color:#22c55e;margin:0 0 16px;font-size:1.1rem;font-weight:700">
        📋 Recent Accounts
      </h2>
      <div style="max-height:320px;overflow-y:auto">
        {recent_html}
      </div>
    </div>

    <!-- Stats Panel -->
    <div class="card" style="padding:24px">
      <h2 style="color:#22c55e;margin:0 0 16px;font-size:1.1rem;font-weight:700">
        📊 Statistics
      </h2>
      <div style="display:flex;flex-direction:column;gap:12px">
        {"".join(f'''
        <div style="display:flex;justify-content:space-between;
                    padding:10px;background:#0f172a;border-radius:8px">
          <span style="color:#94a3b8">{label}</span>
          <span style="font-weight:700;color:{color}">{value}</span>
        </div>
        ''' for label, value, color in [
            ("Total Attempts", stats['total_created'], "#f1f5f9"),
            ("Successful", stats['total_success'], "#22c55e"),
            ("Failed", stats['total_failed'], "#ef4444"),
            ("Tokens Generated", stats['total_tokens'], "#a78bfa"),
            ("Bot Requests", stats['total_requests'], "#60a5fa"),
            ("Banned Proxies", stats['banned_proxies'], "#f87171"),
            ("Proxy Mode", proxy_mode, proxy_color),
            ("Last Created", stats.get('last_created') or 'Never', "#94a3b8"),
        ])}
      </div>
    </div>
  </div>

  <!-- Chart + Manual Create -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">

    <!-- Chart -->
    <div class="card" style="padding:24px">
      <h2 style="color:#22c55e;margin:0 0 16px;font-size:1.1rem;font-weight:700">
        📈 Daily Creations
      </h2>
      <canvas id="chart" style="max-height:200px"></canvas>
    </div>

    <!-- Manual Create -->
    <div class="card" style="padding:24px">
      <h2 style="color:#22c55e;margin:0 0 12px;font-size:1.1rem;font-weight:700">
        ⚡ Manual Create
      </h2>
      <p style="color:#94a3b8;font-size:14px;margin:0 0 16px">
        Create accounts directly from dashboard
      </p>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        {"".join(f'''
        <button onclick="createAccounts({n})"
          style="background:#{'22c55e' if n==1 else '3b82f6' if n==3 else '8b5cf6'};
                 color:white;border:none;padding:10px 20px;border-radius:8px;
                 font-weight:700;cursor:pointer;font-size:14px">
          Create {n}
        </button>
        ''' for n in [1, 3, 5])}
      </div>
      <div id="result"
        style="margin-top:16px;padding:12px;background:#0f172a;
               border-radius:8px;font-size:13px;color:#94a3b8;
               min-height:44px;font-family:monospace">
        Ready to create...
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div style="text-align:center;color:#475569;font-size:13px;padding:20px 0">
    FF Guest Bot — 24/7 on Render.com Free Tier
    &nbsp;|&nbsp; Started: {stats.get('start_time', 'Unknown')}
  </div>

</div>

<script>
// Chart
const ctx = document.getElementById('chart').getContext('2d');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: {labels_js},
    datasets: [{{
      label: 'Accounts Created',
      data: {values_js},
      backgroundColor: '#22c55e55',
      borderColor: '#22c55e',
      borderWidth: 2,
      borderRadius: 5,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});

// Manual create
async function createAccounts(count) {{
  const d = document.getElementById('result');
  d.innerHTML = '⏳ Creating ' + count + ' account(s)...';
  d.style.color = '#f59e0b';
  try {{
    const r = await fetch(
      '/api/create?count=' + count + '&password={password}',
      {{method:'POST'}}
    );
    const data = await r.json();
    d.innerHTML = '✅ Created: ' + data.created + ' | ❌ Failed: ' + data.failed;
    d.style.color = '#22c55e';
    setTimeout(() => location.reload(), 2000);
  }} catch(e) {{
    d.innerHTML = '❌ Error: ' + e.message;
    d.style.color = '#ef4444';
  }}
}}
</script>
</body>
</html>"""

    return _html(html)
