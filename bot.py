# bot.py
# Main Telegram Bot — runs 24/7 on Render.com

import os
import asyncio
import logging
import threading
import uvicorn
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)
from dashboard import app as dashboard_app
from api_creator import create_multiple_guests
from stats_manager import (
    record_request, load_stats,
    get_success_rate, get_today_count
)
from proxy_manager import proxy_manager

load_dotenv()

# ── Config ────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
ADMIN_ID     = int(os.getenv("ADMIN_ID", 0))
MAX_ACCOUNTS = int(os.getenv("MAX_ACCOUNTS", 10))
RENDER_URL   = os.getenv("RENDER_URL", "https://your-app.onrender.com")

logging.basicConfig(
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level   = logging.INFO,
    handlers = [
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ── Dashboard Server Thread ───────────────────────────────────────

def run_dashboard():
    """Run FastAPI dashboard in background thread"""
    port = int(os.getenv("DASHBOARD_PORT", 8080))
    uvicorn.run(
        dashboard_app,
        host    = "0.0.0.0",
        port    = port,
        log_level = "error"
    )


# ── Telegram Command Handlers ─────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    text = (
        f"👋 **Welcome {user.first_name}!**\n\n"
        f"🔥 **Free Fire Silent Guest Bot**\n\n"
        f"**Commands:**\n"
        f"• `/getguest` — Create 1 account\n"
        f"• `/getguest 5` — Create 5 accounts (parallel)\n"
        f"• `/getguest 10` — Create 10 accounts (max)\n"
        f"• `/stats` — Bot statistics\n"
        f"• `/proxies` — Proxy status\n"
        f"• `/dashboard` — Web dashboard link\n"
        f"• `/help` — Show this menu\n\n"
        f"⚡ **Runs 24/7 — No PC needed!**\n"
        f"🌐 Proxy rotation enabled\n"
        f"🛡️ Auto-ban detection active"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    await cmd_start(update, context)


async def cmd_getguest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main command — create guest accounts"""
    user = update.effective_user
    record_request()

    # Parse count argument
    count = 1
    if context.args:
        try:
            count = int(context.args[0])
            count = max(1, min(count, MAX_ACCOUNTS))
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid number!\n"
                "Usage: `/getguest 5`\n"
                f"Max: {MAX_ACCOUNTS} accounts",
                parse_mode='Markdown'
            )
            return

    logger.info(f"User {user.username}({user.id}) requested {count} account(s)")

    # Send working message
    plural = "accounts" if count > 1 else "account"
    eta    = max(15, count * 8)

    status_msg = await update.message.reply_text(
        f"🚀 **Creating {count} Guest {plural.title()}**\n\n"
        f"⏳ Estimated time: ~{eta} seconds\n"
        f"🌐 Proxy rotation: {'✅ Active' if proxy_manager.use_proxies else '⚡ Direct'}\n"
        f"🛡️ Ban detection: ✅ Active\n\n"
        f"_Please wait..._",
        parse_mode='Markdown'
    )

    # Create accounts
    start_time = datetime.now()
    results    = await create_multiple_guests(count)
    elapsed    = round((datetime.now() - start_time).total_seconds(), 1)

    success_results = [r for r in results if r.get("success")]
    failed_results  = [r for r in results if not r.get("success")]

    # Update status message
    await status_msg.edit_text(
        f"✅ **Done in {elapsed}s!**\n"
        f"✅ Success: {len(success_results)}/{count}\n"
        f"❌ Failed: {len(failed_results)}/{count}",
        parse_mode='Markdown'
    )

    # Send each account as separate message
    for i, acc in enumerate(success_results, 1):
        token_icon = "✅" if acc.get("token_generated") else "❌"
        dupe_note  = " _(duplicate)_" if acc.get("save_status") == "dupe" else ""

        msg_text = (
            f"🎮 **Account {i}/{len(success_results)}**{dupe_note}\n\n"
            f"🆔 **UID:** `{acc['uid']}`\n"
            f"🔑 **Password:** `{acc['password']}`\n"
            f"🎟️ **Token:** {token_icon} "
            f"{'Generated' if acc.get('token_generated') else 'Failed'}\n"
            f"📱 **Device:** {acc.get('device', 'Unknown')}\n"
            f"🌐 **Proxy:** `{str(acc.get('proxy_used', 'direct'))[:30]}`\n"
            f"⏰ **Time:** {acc.get('timestamp', '')}"
        )

        # Add JWT token if available (only if it exists)
        if acc.get("jwt_token"):
            jwt_preview = acc["jwt_token"][:50] + "..."
            msg_text += f"\n🔐 **JWT:** `{jwt_preview}`"

        await update.message.reply_text(msg_text, parse_mode='Markdown')
        await asyncio.sleep(0.3)

    # Send failures if any
    if failed_results:
        fail_text = f"⚠️ **{len(failed_results)} Failed:**\n"
        for i, fail in enumerate(failed_results, 1):
            fail_text += f"{i}. {fail.get('error', 'Unknown error')}\n"
        await update.message.reply_text(fail_text, parse_mode='Markdown')

    # Final summary
    stats   = load_stats()
    summary = (
        f"📊 **Session Summary**\n\n"
        f"✅ Created: {len(success_results)}\n"
        f"❌ Failed: {len(failed_results)}\n"
        f"⏱️ Time: {elapsed}s\n"
        f"📦 Total in DB: {stats['total_success']}\n"
        f"📅 Today: {get_today_count()}\n"
        f"📈 Success Rate: {get_success_rate()}%"
    )
    await update.message.reply_text(summary, parse_mode='Markdown')


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistics command"""
    stats       = load_stats()
    proxy_stats = proxy_manager.get_stats()

    text = (
        f"📊 **Bot Statistics**\n\n"
        f"**Account Stats:**\n"
        f"• Total Attempts: {stats['total_created']}\n"
        f"• Successful: {stats['total_success']}\n"
        f"• Failed: {stats['total_failed']}\n"
        f"• Tokens Generated: {stats['total_tokens']}\n"
        f"• Success Rate: {get_success_rate()}%\n"
        f"• Today: {get_today_count()}\n\n"
        f"**Proxy Stats:**\n"
        f"• Total Proxies: {proxy_stats['total_proxies']}\n"
        f"• Available: {proxy_stats['available_proxies']}\n"
        f"• Banned: {proxy_stats['bad_proxies']}\n\n"
        f"**Bot Stats:**\n"
        f"• Total Requests: {stats['total_requests']}\n"
        f"• Started: {stats['start_time']}\n"
        f"• Last Created: {stats['last_created'] or 'Never'}"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proxy status command"""
    stats = proxy_manager.get_stats()

    if stats["total_proxies"] == 0:
        text = (
            "🌐 **Proxy Status**\n\n"
            "⚡ Mode: Direct Connection\n"
            "No proxies configured.\n\n"
            "Add proxies to `proxies.txt` for better success rate."
        )
    else:
        text = (
            f"🌐 **Proxy Status**\n\n"
            f"• Mode: Rotation Active\n"
            f"• Total: {stats['total_proxies']}\n"
            f"• Available: {stats['available_proxies']}\n"
            f"• Banned: {stats['bad_proxies']}\n\n"
            f"✅ Proxy rotation is working!"
        )

    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dashboard link command"""
    password = os.getenv("DASHBOARD_PASSWORD", "admin123")
    url      = f"{RENDER_URL}/dashboard?password={password}"

    text = (
        f"🖥️ **Web Dashboard**\n\n"
        f"🔗 Link: {url}\n\n"
        f"Features:\n"
        f"• Live statistics\n"
        f"• Recent accounts\n"
        f"• Proxy status\n"
        f"• Manual account creation\n"
        f"• Auto-refreshes every 15s"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unknown command handler"""
    await update.message.reply_text(
        "❓ Unknown command.\nUse /help to see all commands."
    )


# ── Bot Initialization ────────────────────────────────────────────

async def post_init(app: Application) -> None:
    """Set bot commands in Telegram menu"""
    commands = [
        BotCommand("start",     "Start the bot"),
        BotCommand("getguest",  "Create guest account(s)"),
        BotCommand("stats",     "View statistics"),
        BotCommand("proxies",   "Check proxy status"),
        BotCommand("dashboard", "Web dashboard link"),
        BotCommand("help",      "Show help"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("✅ Bot commands registered")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not set!")
        return

    # Start dashboard in background thread
    dashboard_thread = threading.Thread(
        target = run_dashboard,
        daemon = True
    )
    dashboard_thread.start()
    logger.info("✅ Dashboard started in background")

    # Build and run bot
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("getguest",  cmd_getguest))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("proxies",   cmd_proxies))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("=" * 55)
    print("  🔥 FF Guest Bot — Full Advanced Version")
    print(f"  📊 Dashboard: {RENDER_URL}/dashboard")
    print(f"  🌐 Proxies: {proxy_manager.get_stats()['total_proxies']} loaded")
    print(f"  🤖 Bot: Running 24/7 on Render.com")
    print("=" * 55)

    app.run_polling(
        allowed_updates   = Update.ALL_TYPES,
        drop_pending_updates = True
    )


if __name__ == "__main__":
    main()