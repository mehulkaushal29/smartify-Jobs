import logging
import re
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ⬇️ includes CHANNEL_ID from .env via config.py
from config import TELEGRAM_BOT_TOKEN, DEFAULT_TZ, DAILY_HOUR, DAILY_MINUTE, CHANNEL_ID
from jobs_api import get_jobs
from ai_tools import get_ai_tools
from database import get_user, upsert_user, all_users
from utils import WELCOME, format_jobs, format_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartify")


# ----------------- Helpers -----------------

def parse_jobs_args(args):
    country = "AU"
    location = None
    tokens = []

    for a in args:
        al = a.lower()
        if al in ("au", "in"):
            country = al.upper()
        elif al.startswith("loc="):
            location = a.split("=", 1)[1]
        else:
            tokens.append(a)

    keyword = " ".join(tokens).strip() or "software engineer"
    return keyword, country, location


def parse_free_text_to_query(text: str):
    t = (text or "").strip()
    t = re.sub(r"[,\.;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    country = "AU"
    location = None

    if re.search(r"\b(au|australia)\b", t, flags=re.I):
        country = "AU"
        t = re.sub(r"\b(au|australia)\b", "", t, flags=re.I)
    if re.search(r"\bindia\b", t, flags=re.I):
        country = "IN"
        t = re.sub(r"\bindia\b", "", t, flags=re.I)

    m = re.search(r"loc=([A-Za-z\s]+)", t)
    if m:
        location = m.group(1).strip()
        t = re.sub(r"loc=[A-Za-z\s]+", "", t).strip()

    keyword = t if t else "software engineer"
    return keyword, country, location


def build_subscribe_keyboard(prefs: dict, daily_time: str) -> InlineKeyboardMarkup:
    def label(key, text):
        return f"{'✅' if prefs.get(key) else '⭕️'} {text}"
    kb = [
        [
            InlineKeyboardButton(label("jobs_au", "Jobs AU"), callback_data="sub:toggle:jobs_au"),
            InlineKeyboardButton(label("jobs_in", "Jobs IN"), callback_data="sub:toggle:jobs_in"),
        ],
        [
            InlineKeyboardButton(label("ai_tools", "AI Tools"), callback_data="sub:toggle:ai_tools"),
        ],
        [
            InlineKeyboardButton("✅ Done (save)", callback_data="sub:done"),
            InlineKeyboardButton("🛑 Unsubscribe all", callback_data="sub:clear"),
        ],
    ]
    footer = [[InlineKeyboardButton(f"⏰ Daily at {daily_time}", callback_data="sub:nop")]]
    return InlineKeyboardMarkup(kb + footer)


def start_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("✅ Subscribe", callback_data="ui:open_subscribe")]]
    if CHANNEL_ID:
        buttons.append([InlineKeyboardButton("📢 Open Channel", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")])
    return InlineKeyboardMarkup(buttons)


# ----------------- Channel posting -----------------

async def post_channel_summary(app):
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID not set — skipping channel post.")
        return

    parts = []

    au = format_jobs(get_jobs("software engineer", "AU"))
    if au.strip():
        parts.append("🔥 <b>AU Jobs</b>:\n\n" + au)

    in_ = format_jobs(get_jobs("software engineer", "IN"))
    if in_.strip():
        parts.append("🔥 <b>India Jobs</b>:\n\n" + in_)

    tools = format_tools(get_ai_tools())
    if tools.strip():
        parts.append("🤖 <b>AI Tools</b>:\n\n" + tools)

    if not parts:
        logger.info("Nothing to post to channel today.")
        return

    text = "\n\n—\n\n".join(parts)

    buttons = [
        [InlineKeyboardButton("🤖 Open Bot / Subscribe", url="https://t.me/smartify_jobs_bot")],
        [InlineKeyboardButton("📢 Join Smartify Jobs", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await app.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=markup,
        )
        logger.info(f"Posted daily summary to channel {CHANNEL_ID}")
    except Exception as e:
        logger.warning(f"Failed to post to channel {CHANNEL_ID}: {e}")


# ----------------- Command Handlers -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id)
    await update.message.reply_text(
        WELCOME,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=start_keyboard(),
    )


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw, cc, loc = parse_jobs_args(context.args)
    results = get_jobs(kw, cc, location=loc)
    header = f"🔎 <b>Jobs for “{kw}” — {cc}</b>" + (f" — {loc}" if loc else "")
    if not results:
        return await update.message.reply_text(
            header + "\n\nNo results found.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    await update.message.reply_text(
        header + "\n\n" + format_jobs(results),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def jobs_au(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id, prefs={"jobs_au": True})
    jobs_list = get_jobs("software engineer", "AU")
    await update.message.reply_text(
        "🔥 <b>Today's AU jobs</b>:\n\n" + format_jobs(jobs_list),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def jobs_in(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id, prefs={"jobs_in": True})
    jobs_list = get_jobs("software engineer", "IN")
    await update.message.reply_text(
        "🔥 <b>Today's India jobs</b>:\n\n" + format_jobs(jobs_list),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def aitools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id, prefs={"ai_tools": True})
    tools = get_ai_tools()
    await update.message.reply_text(
        "🤖 <b>Trending AI tools</b>:\n\n" + format_tools(tools),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def both(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id, prefs={"jobs_au": True, "ai_tools": True})
    jobs_list = get_jobs("software engineer", "AU")
    tools = get_ai_tools()
    msg = "🔥 <b>AU Jobs</b>:\n\n" + format_jobs(jobs_list) + "\n\n—\n\n" + "🤖 <b>AI Tools</b>:\n\n" + format_tools(tools)
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = [a.lower() for a in context.args]

    if args:
        prefs = {"jobs_au": False, "jobs_in": False, "ai_tools": False}
        if "jobs_au" in args: prefs["jobs_au"] = True
        if "jobs_in" in args: prefs["jobs_in"] = True
        if "ai_tools" in args: prefs["ai_tools"] = True
        upsert_user(user_id, prefs=prefs)
        pretty = ", ".join([k for k, v in prefs.items() if v]) or "(none)"
        return await update.message.reply_text(
            f"Subscribed to: {pretty}.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    user = get_user(user_id)
    prefs = user.get("prefs", {"jobs_au": False, "jobs_in": False, "ai_tools": False})
    daily_time = f"{DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {DEFAULT_TZ}"
    await update.message.reply_text(
        "Choose what you want daily:",
        reply_markup=build_subscribe_keyboard(prefs, daily_time),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ui:open_subscribe":
        user = get_user(query.from_user.id)
        prefs = user.get("prefs", {"jobs_au": False, "jobs_in": False, "ai_tools": False})
        daily_time = f"{DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {DEFAULT_TZ}"
        return await query.edit_message_text(
            "Choose what you want to receive daily:",
            reply_markup=build_subscribe_keyboard(prefs, daily_time),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    user_id = query.from_user.id
    user = get_user(user_id)
    prefs = user.get("prefs", {"jobs_au": False, "jobs_in": False, "ai_tools": False})

    data = query.data

    if data == "sub:nop":
        return

    if data == "sub:clear":
        prefs = {"jobs_au": False, "jobs_in": False, "ai_tools": False}
        upsert_user(user_id, prefs=prefs)
        return await query.edit_message_text(
            "Unsubscribed from all.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    if data == "sub:done":
        upsert_user(user_id, prefs=prefs)
        pretty = ", ".join([k for k, v in prefs.items() if v]) or "(none)"
        return await query.edit_message_text(
            f"Saved: {pretty}.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    if data.startswith("sub:toggle:"):
        key = data.split(":", 2)[-1]
        prefs[key] = not prefs.get(key, False)
        daily_time = f"{DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {DEFAULT_TZ}"
        return await query.edit_message_reply_markup(
            reply_markup=build_subscribe_keyboard(prefs, daily_time)
        )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user(user_id, prefs={"jobs_au": False, "jobs_in": False, "ai_tools": False})
    await update.message.reply_text(
        "Unsubscribed from all daily pushes.",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    p = user["prefs"]
    msg = (
        "Your preferences:\n"
        f"• jobs_au: {p['jobs_au']}\n"
        f"• jobs_in: {p['jobs_in']}\n"
        f"• ai_tools: {p['ai_tools']}\n"
        f"Daily: {DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {DEFAULT_TZ}"
    )
    await update.message.reply_text(msg)


async def settz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text(
            "Send a valid timezone, e.g. /settz Asia/Kolkata"
        )

    tz_str = context.args[0]

    # validate using ZoneInfo
    try:
        ZoneInfo(tz_str)
    except Exception:
        return await update.message.reply_text(
            "Invalid timezone. Try Asia/Kolkata or Australia/Melbourne."
        )

    upsert_user(update.effective_user.id, tz=tz_str)
    await update.message.reply_text(
        f"Timezone set to {tz_str}."
    )


async def pushnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await push_daily_job(context)
    await update.message.reply_text("Pushed now.")


async def postchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_ID:
        return await update.message.reply_text("CHANNEL_ID not set in .env.")
    await post_channel_summary(context.application)
    await update.message.reply_text("Posted to channel.")


# ----------------- Text Search -----------------

async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    kw, cc, loc = parse_free_text_to_query(text)
    results = get_jobs(kw, cc, location=loc)
    if not results:
        try_cc = "IN" if cc == "AU" else "AU"
        results = get_jobs(kw, try_cc, location=loc)
        if results:
            cc = try_cc
    header = f"🔎 <b>Jobs for “{kw}” — {cc}</b>" + (f" — {loc}" if loc else "")
    msg = header + "\n\n" + (format_jobs(results) if results else "No results found.")
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


# ----------------- Daily Push -----------------

async def push_daily_job(context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    logger.info("Running daily push job…")

    for row in all_users():
        uid = row["user_id"]
        p = row.get("prefs", {})
        if not any(p.values()):
            continue

        parts = []
        if p.get("jobs_au"):
            parts.append("🔥 <b>AU Jobs</b>:\n\n" + format_jobs(get_jobs("software engineer", "AU")))
        if p.get("jobs_in"):
            parts.append("🔥 <b>India Jobs</b>:\n\n" + format_jobs(get_jobs("software engineer", "IN")))
        if p.get("ai_tools"):
            parts.append("🤖 <b>AI Tools</b>:\n\n" + format_tools(get_ai_tools()))

        if parts:
            try:
                await app.bot.send_message(
                    chat_id=uid,
                    text="\n\n—\n\n".join(parts),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Failed to push to {uid}: {e}")

    await post_channel_summary(app)


async def on_startup(application):
    tz = ZoneInfo(DEFAULT_TZ)  # UPDATED — no pytz
    application.job_queue.run_daily(
        push_daily_job,
        time=dtime(hour=DAILY_HOUR, minute=DAILY_MINUTE, tzinfo=tz),
        name="daily_push"
    )
    logger.info(f"Daily job scheduled for {DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {DEFAULT_TZ}")


def run():
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing. Check your .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("jobs_au", jobs_au))
    app.add_handler(CommandHandler("jobs_in", jobs_in))
    app.add_handler(CommandHandler("aitools", aitools))
    app.add_handler(CommandHandler("both", both))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("prefs", prefs))
    app.add_handler(CommandHandler("settz", settz))
    app.add_handler(CommandHandler("pushnow", pushnow))
    app.add_handler(CommandHandler("postchannel", postchannel))

    # Buttons
    app.add_handler(CallbackQueryHandler(sub_callback, pattern=r"^(ui:open_subscribe|sub:.*)$"))

    # Plain text search
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))

    # Daily job
    app.post_init = on_startup

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    run()

