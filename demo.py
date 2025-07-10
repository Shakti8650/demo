# gabbar_bot.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import os

# ─────────────── GLOBALS ───────────────
users = {}
waiting_users = set()
active_chats = {}
report_history = []
admins = [7460406130]  # Replace with real admin Telegram ID(s)

LANGUAGES = {
    "en": "🇬🇧 English",
    "hi": "🇮🇳 Hindi",
    "es": "🇪🇸 Spanish"
}

GENDER, LANGUAGE = range(2)
AGE, TYPING_LANGUAGE = range(2)

# ─────────────── BLOCK SYSTEM ───────────────
blocked_users = {}

def is_currently_blocked(uid: int) -> tuple[bool, str | None]:
    info = blocked_users.get(uid)
    if not info:
        return False, None
    if datetime.utcnow() < info["until"]:
        until_str = info["until"].strftime("%d %B %Y at %H:%M UTC")
        reason = info.get("reason", "Rule Violation")
        msg = (
            "🚫 You have been banned due to rules violation.\n\n"
            "❌ It is prohibited to:\n"
            "• Sell or advertise\n"
            "• Send group/channel invites\n"
            "• Share pornographic content\n"
            "• Ask for money or personal info\n\n"
            f"📝 Reason: {reason}\n"
            f"⏰ You will be able to use the chat again at {until_str}.\n\n"
            "⚠️ If you believe this was a mistake, contact the admin."
        )
        return True, msg
    return False, None

BLOCK_STEPS = [24, 48, 96, 480, 720]

# ─────────────── PROFILE CHECK ───────────────
def is_profile_complete(uid: int) -> bool:
    return "gender" in users[uid] and "language" in users[uid]

def is_profile_complete_dict(d: dict) -> bool:
    return "gender" in d and "language" in d

# ─────────────── CALLBACKS PLACEHOLDERS ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass  # already implemented elsewhere

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def set_language_initial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def set_language_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

# (Paste your real logic of these functions here in actual implementation)

# ─────────────── CANCEL SETTINGS ───────────────
async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await query.message.reply_text(msg)
        return
    await query.answer()
    if user_id in active_chats:
        follow = "🔎 You are currently in a chat.\n💬 Use /stop to end or /next to skip."
    else:
        follow = "❌ You are not in a chat.\n💬 Use /next to start chatting."
    await query.edit_message_text(f"❌ Cancelled.\n{follow}")
    return ConversationHandler.END

# ─────────────── MESSAGE HANDLER ───────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await update.message.reply_text(msg)
        return
    if user_id not in users:
        users[user_id] = {}
    u = users[user_id]
    if not is_profile_complete(user_id):
        await update.message.reply_text("🚫 Please complete your profile first.")
        if "gender" not in u:
            buttons = [[
                InlineKeyboardButton("🚹 Male", callback_data="set_gender:Male"),
                InlineKeyboardButton("🚺 Female", callback_data="set_gender:Female"),
                InlineKeyboardButton("⚧ Other", callback_data="set_gender:Other"),
            ]]
            await update.message.reply_text(
                "👇 Please select your gender. ⚠️ Once set, cannot be changed.",
                reply_markup=InlineKeyboardMarkup(buttons))
            return
        if "language" not in u:
            buttons = [[InlineKeyboardButton(txt, callback_data=f"set_lang:{code}")]
                       for code, txt in LANGUAGES.items()]
            await update.message.reply_text(
                "👇 Please select your language:\n🔸 You can change this later using /settings",
                reply_markup=InlineKeyboardMarkup(buttons))
            return
        return

    if user_id in active_chats:
        partner_id = active_chats[user_id]
        msg = update.message
        if msg.text:
            await context.bot.send_message(partner_id, msg.text)
        elif msg.photo:
            await context.bot.send_photo(partner_id, msg.photo[-1].file_id, caption=msg.caption)
        elif msg.sticker:
            await context.bot.send_sticker(partner_id, msg.sticker.file_id)
        elif msg.voice:
            await context.bot.send_voice(partner_id, msg.voice.file_id)
        elif msg.video:
            await context.bot.send_video(partner_id, msg.video.file_id, caption=msg.caption)
        elif msg.animation:
            await context.bot.send_animation(partner_id, msg.animation.file_id, caption=msg.caption)
        elif msg.audio:
            await context.bot.send_audio(partner_id, msg.audio.file_id, caption=msg.caption)
        elif msg.document:
            await context.bot.send_document(partner_id, msg.document.file_id, caption=msg.caption)
    elif user_id in waiting_users:
        await update.message.reply_text(
            "⏳ Searching for a partner…\n"
            "❌ You are not in a chat yet.\n"
            "💤 To stop searching, use /stop."
        )
    else:
        await update.message.reply_text("❌ You are not in a chat.\n💬 Use /next to find a partner.")

# [Continue with the rest of your provided code...]
# Due to token limits, I will send the remaining part (Report system + Admin Panel + Handlers + Web Server) in next message.
# ─────────────── REPORT SYSTEM ───────────────
REPORT_REASONS = {
    "Advertising": "📢 Advertising",
    "Selling":     "💰 Selling",
    "Child":       "🚫 Child Porn",
    "Begging":     "🙏 Begging",
    "Insult":      "😡 Insulting",
    "Violence":    "⚔️ Violence",
    "Vulgar":      "🤬 Vulgar Partner"
}

async def open_report_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    partner_id = context.user_data.get("last_partner")
    if not partner_id:
        await query.answer("There is no partner to report.", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(txt, callback_data=f"rep_reason:{key}")]
        for key, txt in REPORT_REASONS.items()
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="rep_cancel")])
    await query.edit_message_text(
        "⚠️ Select a reason to report your previous partner:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "rep_cancel":
        await query.edit_message_text("❌ Report cancelled.\n💬 Use /next to start chatting.")
        return
    reason_key = query.data.split(":")[1]
    reason_txt = REPORT_REASONS[reason_key]
    partner_id = context.user_data.pop("last_partner", None)
    await query.edit_message_text("✅ Report submitted. Thank you!\n💬 Use /next to start chatting.")
    for admin in admins:
        await context.bot.send_message(
            admin,
            f"🚨 Report Received\nReporter: {user_id}\nAgainst: {partner_id}\nReason: {reason_txt}"
        )
    report_history.append({
        "reporter": user_id,
        "reported": partner_id,
        "reason": reason_txt,
        "time": datetime.utcnow(),
        "handled": False
    })

# ─────────────── ADMIN PANEL ───────────────
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        return
    root_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Reports",       callback_data="admin:reports")],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="admin:blocked")],
        [InlineKeyboardButton("📊 Stats",         callback_data="admin:stats")],
    ])
    await update.effective_message.reply_text(
        "🛡 *Admin Panel*", reply_markup=root_buttons, parse_mode="Markdown"
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if uid not in admins:
        return
    data = query.data

    if data == "admin:back":
        try:
            await query.message.delete()
        except: pass
        await admin(update, context)
        return

    if data == "admin:reports":
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 All open",    callback_data="rep_filter:all")],
            [InlineKeyboardButton("🗓 Last 7 days", callback_data="rep_filter:7d")],
            [InlineKeyboardButton("⚠️ 3+ reports",  callback_data="rep_filter:3+")],
            [InlineKeyboardButton("🔙 Back",        callback_data="admin:back")],
        ])
        await query.edit_message_text("📋 *Open Reports* – choose filter:",
                                      reply_markup=buttons, parse_mode="Markdown")
        return

    if data == "admin:blocked":
        if not blocked_users:
            await query.edit_message_text("✅ No users are currently blocked.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:back")]]))
            return
        rows = []
        for uid_, info in blocked_users.items():
            hrs_left = int((info["until"] - datetime.utcnow()).total_seconds() // 3600)
            rows.append([InlineKeyboardButton(f"{uid_} ({hrs_left}h)", callback_data=f"blk_info:{uid_}")])
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])
        await query.edit_message_text("🚫 *Blocked Users* (UID – hours left):",
                                      reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")
        return

    if data == "admin:stats":
        total_users = len(users)
        profiles_done = sum(1 for u in users.values() if is_profile_complete_dict(u))
        active = len(active_chats) // 2
        searching = len(waiting_users)
        new_today = sum(1 for u in users.values()
                        if u.get('created') == datetime.utcnow().date().isoformat())
        online = len({*active_chats.keys(), *waiting_users})
        blocked_cnt = len(blocked_users)
        total_reports = len([r for r in report_history if not r["handled"]])
        text = (
            "📊 *Gabbar Chat Stats:*\n"
            f"👥 Total Users: {total_users}\n"
            f"✅ Profiles Completed: {profiles_done}\n"
            f"💬 Active Chats Right Now: {active}\n"
            f"🔍 Users Searching (Waiting): {searching}\n"
            f"🆕 New Users Today: {new_today}\n"
            f"🧑‍💻 Currently Online: {online}\n"
            f"🚫 Blocked Users: {blocked_cnt}\n"
            f"📩 Total Open Reports: {total_reports}"
        )
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:back")]]))
        return

    if data.startswith("rep_filter:"):
        flt = data.split(":")[1]
        open_reports = [r for r in report_history if not r["handled"]]
        if flt == "7d":
            cutoff = datetime.utcnow() - timedelta(days=7)
            open_reports = [r for r in open_reports if r["time"] >= cutoff]
        if flt == "3+":
            counts = {}
            for r in open_reports:
                counts[r["reported"]] = counts.get(r["reported"], 0) + 1
            open_reports = [r for r in open_reports if counts[r["reported"]] >= 3]
        if not open_reports:
            await query.edit_message_text("🎉 No reports in this filter.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:reports")]]))
            return
        rows = [[InlineKeyboardButton(str(r["reported"]), callback_data=f"rep_info:{r['reported']}")]
                for r in open_reports[:50]]
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin:reports")])
        await query.edit_message_text("📋 *Select a user to review:*",
                                      reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")
        return

    if data.startswith("rep_info:"):
        rid = int(data.split(":")[1])
        user_reports = [r for r in report_history if r["reported"] == rid]
        total = len(user_reports)
        latest = user_reports[-1]
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Block", callback_data=f"blk_do:{rid}")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin:reports")]
        ])
        await query.edit_message_text(
            f"🗒 *Reports for* `{rid}`\n"
            f"Total reports: {total}\n"
            f"Last reason : {latest['reason']}\n"
            f"Last time   : {latest['time'].strftime('%Y-%m-%d %H:%M')}",
            parse_mode="Markdown", reply_markup=btns)
        return

    if data.startswith("blk_info:"):
        rid = int(data.split(":")[1])
        info = blocked_users[rid]
        hrs_left = int((info["until"] - datetime.utcnow()).total_seconds() // 3600)
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Unblock", callback_data=f"blk_un:{rid}")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin:blocked")]
        ])
        await query.edit_message_text(
            f"🚫 *Blocked user* `{rid}`\n"
            f"Reason : {info['reason']}\n"
            f"Times  : {info['count']}\n"
            f"Ends   : {info['until'].strftime('%Y-%m-%d %H:%M')} ({hrs_left}h left)",
            parse_mode="Markdown", reply_markup=btns)
        return

    if data.startswith("blk_do:"):
        rid = int(data.split(":")[1])
        cnt = blocked_users.get(rid, {}).get("count", 0)
        hours = BLOCK_STEPS[min(cnt, len(BLOCK_STEPS) - 1)]
        until = datetime.utcnow() + timedelta(hours=hours)
        blocked_users[rid] = {"until": until, "count": cnt + 1, "reason": "Admin"}
        for r in report_history:
            if r["reported"] == rid and not r["handled"]:
                r["handled"] = True
        await query.edit_message_text(f"🚫 User `{rid}` blocked for {hours} hours.",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:reports")]]))
        return

    if data.startswith("blk_un:"):
        rid = int(data.split(":")[1])
        blocked_users.pop(rid, None)
        await query.edit_message_text(f"✅ User `{rid}` unblocked.",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:blocked")]]))
        return

# ─────────────── MAIN & RUN ───────────────
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        GENDER: [CallbackQueryHandler(set_gender, pattern="^set_gender:")],
        LANGUAGE: [CallbackQueryHandler(set_language_initial, pattern="^set_lang:")]
    },
    fallbacks=[],
    allow_reentry=True,
)

settings_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(setting_callback, pattern="^(set_age|change_language)$")],
    states={
        AGE: [CallbackQueryHandler(set_age, pattern="^age:")],
        TYPING_LANGUAGE: [CallbackQueryHandler(set_language_change, pattern="^set_lang:")]
    },
    fallbacks=[CallbackQueryHandler(cancel_settings, pattern="^cancel_settings$")]
)

if __name__ == "__main__":
    TOKEN = "8073774821:AAG5Atukmg0yFWsbzV-oJn4KLZ2fWV63fBQ"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(conv)
    app.add_handler(settings_conv)
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("me", me))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(cancel_settings, pattern="^cancel_settings$"))
    app.add_handler(CallbackQueryHandler(open_report_menu, pattern="^report:open$"))
    app.add_handler(CallbackQueryHandler(handle_report_reason, pattern="^rep_reason:"))
    app.add_handler(CallbackQueryHandler(handle_report_reason, pattern="^rep_cancel$"))
    app.add_handler(CommandHandler("admin", admin, filters=filters.User(admins)))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(admin:|rep_filter:|rep_info:|blk_).*"))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    print("✅ Gabbar Chat is starting...")

    flask_app = Flask(__name__)

    @flask_app.route('/')
    def home():
        return "✅ Bot is alive!"

    def run_flask():
        flask_app.run(host='0.0.0.0', port=8080)

    Thread(target=run_flask).start()
    app.run_polling()

