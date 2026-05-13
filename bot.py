# bot.py — Main entry point
import os
import asyncio
import logging
import threading
import uvicorn
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler,
    ContextTypes, MessageHandler, filters
)
from dashboard import app as dashboard_app
from api_creator import create_multiple_guests
from stats_manager import (
    record_request, load_stats,
    get_success_rate, get_today_count,
    get_total_accounts
)
from proxy_manager import proxy_manager

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
ADMIN_ID     = int(os.getenv("ADMIN_ID", 0))
MAX_ACCOUNTS = int(os.getenv("MAX_ACCOUNTS", 10))
RENDER_URL   = os.getenv("RENDER_URL", "https://ff-guest-bot.onrender.com")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ── Dashboard Thread ──────────────────────────────────────────────

def _run_dashboard():
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        dashboard_app,
        host="0.0.0.0",
        port=port,
        log_level="warning"
    )


# ── Command Handlers ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 **Free Fire Silent Guest Bot**\n\n"
        "**Commands:**\n"
        "• `/getguest` — Create 1 account\n"
        "• `/getguest 5` — Create 5 in parallel\n"
        "• `/getguest 10` — Create 10 (max)\n"
        "• `/stats` — Statistics\n"
        "• `/proxies` — Proxy status\n"
        "• `/scrapeproxies` — Auto-scrape free proxies\n"
        "• `/dashboard` — Web dashboard\n\n"
        "⚡ Runs 24/7 — No PC needed!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_getguest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_request()

    count = 1
    if context.args:
        try:
            count = max(1, min(int(context.args[0]), MAX_ACCOUNTS))
        except ValueError:
            await update.message.reply_text(
                f"❌ Use: `/getguest 5` (max {MAX_ACCOUNTS})",
                parse_mode="Markdown"
            )
            return

    logger.info(f"User {update.effective_user.id} → {count} account(s)")

    plural = "accounts" if count > 1 else "account"
    status = await update.message.reply_text(
        f"🚀 **Creating {count} guest {plural}...**\n"
        f"🌐 Proxy: {'✅ Rotating' if proxy_manager.use_proxies else '⚡ Direct'}\n"
        f"🛡️ Ban detection: ✅\n"
        f"⏳ Please wait...",
        parse_mode="Markdown"
    )

    t0      = datetime.now()
    results = await create_multiple_guests(count)
    elapsed = round((datetime.now() - t0).total_seconds(), 1)

    ok   = [r for r in results if r.get("success")]
    fail = [r for r in results if not r.get("success")]

    await status.edit_text(
        f"{'✅' if ok else '❌'} **Done in {elapsed}s**\n"
        f"✅ Success: {len(ok)}/{count}\n"
        f"❌ Failed:  {len(fail)}/{count}",
        parse_mode="Markdown"
    )

    # Send each success
    for i, acc in enumerate(ok, 1):
        tok_icon = "✅" if acc.get("token_generated") else "❌"
        dupe     = " _(already saved)_" if acc.get("save_status") == "dupe" else ""
        text = (
            f"🎮 **Account {i}/{len(ok)}**{dupe}\n\n"
            f"🆔 **UID:** `{acc['uid']}`\n"
            f"🔑 **Password:** `{acc['password']}`\n"
            f"🎟️ **Token:** {tok_icon} "
            f"{'Generated' if acc.get('token_generated') else 'Failed'}\n"
            f"📱 **Device:** {acc.get('device','Unknown')}\n"
            f"⏰ **Time:** {acc.get('timestamp','')}"
        )
        if acc.get("jwt_token"):
            short = acc["jwt_token"][:60] + "..."
            text += f"\n🔐 **JWT:** `{short}`"
        await update.message.reply_text(text, parse_mode="Markdown")
        await asyncio.sleep(0.2)

    # Send failures
    if fail:
        errs = "\n".join(
            f"{i}. {r.get('error','Unknown')}"
            for i, r in enumerate(fail, 1)
        )
        await update.message.reply_text(
            f"⚠️ **{len(fail)} Failed:**\n{errs}",
            parse_mode="Markdown"
        )

    # Summary
    await update.message.reply_text(
        f"📊 **Summary**\n\n"
        f"✅ This session: {len(ok)}\n"
        f"📦 Total in DB: {get_total_accounts()}\n"
        f"📅 Today total: {get_today_count()}\n"
        f"📈 Success rate: {get_success_rate()}%\n"
        f"⏱️ Time taken: {elapsed}s",
        parse_mode="Markdown"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s  = load_stats()
    ps = proxy_manager.get_stats()
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"**Accounts:**\n"
        f"• Total Attempts: {s['total_created']}\n"
        f"• Successful: {s['total_success']}\n"
        f"• Failed: {s['total_failed']}\n"
        f"• Tokens: {s['total_tokens']}\n"
        f"• Success Rate: {get_success_rate()}%\n"
        f"• Today: {get_today_count()}\n"
        f"• Total in DB: {get_total_accounts()}\n\n"
        f"**Proxies:**\n"
        f"• Total: {ps['total_proxies']}\n"
        f"• Available: {ps['available_proxies']}\n"
        f"• Banned: {ps['bad_proxies']}\n\n"
        f"**Bot:**\n"
        f"• Requests: {s['total_requests']}\n"
        f"• Started: {s['start_time']}\n"
        f"• Last created: {s.get('last_created') or 'Never'}",
        parse_mode="Markdown"
    )


async def cmd_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ps = proxy_manager.get_stats()
    if ps["total_proxies"] == 0:
        text = (
            "🌐 **Proxy Status**\n\n"
            "Mode: ⚡ Direct Connection\n\n"
            "No proxies in proxies.txt\n"
            "Use /scrapeproxies to auto-get free proxies"
        )
    else:
        text = (
            f"🌐 **Proxy Status**\n\n"
            f"Mode: 🔄 Rotation Active\n"
            f"• Total: {ps['total_proxies']}\n"
            f"• Available: {ps['available_proxies']}\n"
            f"• Banned this session: {ps['bad_proxies']}"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_scrapeproxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 Scraping free proxies from public lists..."
    )
    new = await proxy_manager.scrape_free_proxies()
    await update.message.reply_text(
        f"✅ Scraped **{len(new)}** new proxies!\n"
        f"Total available: {proxy_manager.get_stats()['available_proxies']}",
        parse_mode="Markdown"
    )


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw  = os.getenv("DASHBOARD_PASSWORD", "admin123")
    url = f"{RENDER_URL}/dashboard?password={pw}"
    await update.message.reply_text(
        f"🖥️ **Web Dashboard**\n\n"
        f"🔗 {url}\n\n"
        f"• Live statistics\n"
        f"• Recent accounts\n"
        f"• Manual create\n"
        f"• Auto-refreshes every 15s",
        parse_mode="Markdown"
    )


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Unknown command. Use /start for help."
    )


# ── Setup & Run ───────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start",         "Start the bot"),
        BotCommand("getguest",      "Create guest account(s)"),
        BotCommand("stats",         "View statistics"),
        BotCommand("proxies",       "Check proxy status"),
        BotCommand("scrapeproxies", "Auto-scrape free proxies"),
        BotCommand("dashboard",     "Web dashboard link"),
    ])
    logger.info("✅ Commands registered")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in .env!")
        return

    # Start dashboard in background
    t = threading.Thread(target=_run_dashboard, daemon=True)
    t.start()
    logger.info("✅ Dashboard started")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_start))
    app.add_handler(CommandHandler("getguest",      cmd_getguest))
    app.add_handler(CommandHandler("stats",         cmd_stats))
    app.add_handler(CommandHandler("proxies",       cmd_proxies))
    app.add_handler(CommandHandler("scrapeproxies", cmd_scrapeproxies))
    app.add_handler(CommandHandler("dashboard",     cmd_dashboard))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("=" * 55)
    print("  🔥 FF Guest Bot — Advanced Edition")
    print(f"  📊 Dashboard: {RENDER_URL}/dashboard")
    print(f"  🌐 Proxies: {proxy_manager.get_stats()['total_proxies']}")
    print("=" * 55)

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
