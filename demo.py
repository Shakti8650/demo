# ✅ Final Full Version of Gabbar Chat Bot
# Includes all features: gender, language, optional age, full commands, reporting, and admin panel.

import logging
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
                          ConversationHandler, CallbackQueryHandler)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States
GENDER, LANGUAGE, AGE, TYPING_LANGUAGE = range(4)

# In-memory data
users = {}
waiting_users = []
active_chats = {}
report_history = []   # each dict: {"reporter":uid,"reported":uid,"reason":txt,"time":datetime, "handled":False}
admins = [7460406130]  # Replace with your Telegram user ID
blocked_users = set()
daily_matches = {}

GENDER_EMOJI = {'Male': '🚹', 'Female': '🚺', 'Other': '⚧'}
LANGUAGES = {
    'hi': '🇮🇳 Hindi', 'en': '🇺🇸 English', 'ja': '🇯🇵 Japanese', 'ko': '🇰🇷 Korean',
    'id': '🇮🇩 Indonesian', 'zh': '🇨🇳 Chinese', 'ru': '🇷🇺 Russian'
}

# Utils
def get_profile(user_id):
    u = users[user_id]
    gender = f"{GENDER_EMOJI.get(u['gender'], '')} {u['gender']}"
    language = LANGUAGES.get(u['language'], u['language'])
    age = f"{u['age']}" if 'age' in u else "Not set"
    return f"👤 Your Profile:\n🔹Gender: {gender}\n🔹Language: {language}\n🔹Age: {age}"

def is_profile_complete(user_id):
    return 'gender' in users[user_id] and 'language' in users[user_id]

def increase_match_count():
    today = datetime.now().date().isoformat()
    daily_matches[today] = daily_matches.get(today, 0) + 1

# ── /start handler ────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await update.message.reply_text(msg)
        return

    # ensure user dict exists
    if user_id not in users:
        users[user_id] = {}
    u = users[user_id]

    # ── 1) PROFILE INCOMPLETE ────────────────────────────────
    if not is_profile_complete(user_id):
        await update.message.reply_text("🚫 Please complete your profile first.")

        # ask for gender if missing
        if "gender" not in u:
            buttons = [[
                InlineKeyboardButton("🚹 Male",   callback_data="set_gender:Male"),
                InlineKeyboardButton("🚺 Female", callback_data="set_gender:Female"),
                InlineKeyboardButton("⚧ Other",  callback_data="set_gender:Other"),
            ]]
            await update.message.reply_text(
                "👇 Please select your gender. ⚠️ Once set, cannot be changed.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return GENDER

        # ask for language if gender present but language missing
        if "language" not in u:
            buttons = [[InlineKeyboardButton(name, callback_data=f"set_lang:{code}")]
                       for code, name in LANGUAGES.items()]
            context.chat_data["via_start"] = True
            
            await update.message.reply_text(
                """👇 Please select your language:
  🔸 You can change this later using /settings""",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return LANGUAGE

        # Nothing else to do
        return ConversationHandler.END

    # ── 2) PROFILE COMPLETE & ALREADY IN CHAT ────────────────
    if user_id in active_chats:
        await update.message.reply_text(
            "✅ You're already in a chat.\n"
            "💬 Use /stop to end or /next to find a new partner."
        )
        return ConversationHandler.END

    # ── 3) PROFILE COMPLETE & NOT IN CHAT → behave like /next ─
    await update.message.reply_text(
        "⏳ Waiting for a partner...\n"
        "💬 Use /stop to cancel."
    )
    await find_partner(user_id, context)
    return ConversationHandler.END

# Gender handler
async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    gender = query.data.split(':')[1]
    users[user_id]['gender'] = gender
    buttons = [[InlineKeyboardButton(name, callback_data=f'set_lang:{code}')]
               for code, name in LANGUAGES.items()]
    await query.edit_message_text(
        "🌐 Please select your language:\n\n🔸 You can change this later using /settings",
        reply_markup=InlineKeyboardMarkup(buttons))
    return LANGUAGE

# 🔹 First-time language selection
async def set_language_initial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = query.data.split(':')[1]
    users[user_id]['language'] = lang
    await query.edit_message_text(f"✅ Language set to: {LANGUAGES[lang]}\n\n✅ Your profile is complete.")
    await context.bot.send_message(user_id, "⏳ Waiting for a partner...\n💬 Use /stop to cancel or /next to retry.")
    await find_partner(user_id, context)
    return ConversationHandler.END

# 🔹 Settings से language बदलना
async def set_language_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = query.data.split(':')[1]
    users[user_id]['language'] = lang

    if user_id in active_chats:
        await query.edit_message_text(
            f"🌐 Language updated to: {LANGUAGES[lang]}\n"
            "💬 You are still in a chat.\n💬 Use /stop to end or /next to skip."
        )
    else:
        await query.edit_message_text(
            f"🌐 Language updated to: {LANGUAGES[lang]}\n💬 Use /next to start chatting."
        )

    return ConversationHandler.END

# ────────── Language handler ──────────
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # 🔒 Block check
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await query.message.reply_text(msg)
        return

    lang = query.data.split(':')[1]
    users[user_id]['language'] = lang

    # क्या यह /start के दौरान आया था?
    if context.chat_data.get("via_start"):
        # Profile अभी-अभी पूरी हुई, तो search शुरू कराओ
        await query.edit_message_text(
            f"✅ Language set to: {LANGUAGES[lang]}\n\n✅ Your profile is complete."
        )
        await context.bot.send_message(
            user_id,
            "⏳ Waiting for a partner...\n💬 Use /stop to cancel or /next to retry."
        )
        await find_partner(user_id, context)
        context.chat_data["via_start"] = False      # फ्लैग हटा दो (future updates के लिये)
    else:
        # Settings से language update हुआ है — सिर्फ़ update मेसेज
        await query.edit_message_text(f"✅ Language updated to: {LANGUAGES[lang]}")
        if user_id in active_chats:
            await query.message.reply_text(
                "💬 You are still in a chat.\n💬 Use /stop to end or /next to skip."
            )
        else:
            await query.message.reply_text("💬 Use /next to start chatting.")

    return ConversationHandler.END

# ─────────── Match-making helper ───────────
async def find_partner(user_id, context):
    if user_id in waiting_users:
        return

    for partner_id in waiting_users:
        if partner_id != user_id and partner_id not in blocked_users:
            waiting_users.remove(partner_id)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            increase_match_count()

            # 🔹 दोनों user की last_partner सेट करो (for /report)
            context.user_data["last_partner"] = partner_id
            if "last_partner" not in context.chat_data:
                context.chat_data["last_partner"] = {}
            context.chat_data["last_partner"][partner_id] = user_id

            await context.bot.send_message(user_id, format_match_message(partner_id))
            await context.bot.send_message(partner_id, format_match_message(user_id))
            return

    waiting_users.append(user_id)

def format_match_message(uid):
    u = users[uid]
    return ("✨ You've got a match! ✨\n\nPartner found:\n"
            f"🔹Gender: {GENDER_EMOJI[u['gender']]} {u['gender']}\n"
            f"🔹Language: {LANGUAGES[u['language']]}\n"
            f"🔹Age: {u.get('age', 'Not set')}\n\n"
            "🔸 /next — find a new partner\n🔸 /stop — stop this chat")

# ─────────────  /next  ──────────────
async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # 🔒 Block-guard
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
                InlineKeyboardButton("🚹 Male",   callback_data="set_gender:Male"),
                InlineKeyboardButton("🚺 Female", callback_data="set_gender:Female"),
                InlineKeyboardButton("⚧ Other",  callback_data="set_gender:Other"),
            ]]
            await update.message.reply_text("👇 Please select your gender. ⚠️ Once set, cannot be changed.",
                                            reply_markup=InlineKeyboardMarkup(buttons))
            return
        if "language" not in u:
            buttons = [[InlineKeyboardButton(txt, callback_data=f'set_lang:{code}')]
                       for code, txt in LANGUAGES.items()]
            await update.message.reply_text(
                "👇 Please select your language:\n🔸 You can change this later using /settings",
                reply_markup=InlineKeyboardMarkup(buttons))
            return
        return

    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)

        # Save last partner for both users
        context.user_data["last_partner"] = partner_id
        if "last_partner" not in context.chat_data:
            context.chat_data["last_partner"] = {}
        context.chat_data["last_partner"][partner_id] = user_id

        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚩 Report", callback_data="report:open")]])
        await context.bot.send_message(
            partner_id,
            "❌ Your partner left the chat.\n💬 Use /next to find someone new.",
            reply_markup=btn
        )
        await update.message.reply_text(
            "✅ You left the chat.\n⏳ Searching for a new partner …",
            reply_markup=btn
        )
    else:
        await update.message.reply_text("⏳ Waiting for a partner...\n💬 Use /stop to cancel.")

    await find_partner(user_id, context)

# ─────────────  /stop  ──────────────
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 🔒 Block-guard
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
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        if "language" not in u:
            buttons = [[InlineKeyboardButton(txt, callback_data=f'set_lang:{code}')] for code, txt in LANGUAGES.items()]
            await update.message.reply_text(
                "👇 Please select your language:\n🔸 You can change this later using /settings",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        return

    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)

        # Save last partner for both users
        context.user_data["last_partner"] = partner_id
        if "last_partner" not in context.chat_data:
            context.chat_data["last_partner"] = {}
        context.chat_data["last_partner"][partner_id] = user_id

        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚩 Report", callback_data="report:open")]])
        await context.bot.send_message(
            partner_id,
            "❌ Your partner ended the chat.\n💬 Use /next to find someone new.",
            reply_markup=btn
        )
        await update.message.reply_text(
            "✅ Chat stopped.\n💬 Use /next to chat again.",
            reply_markup=btn
        )
    else:
        await update.message.reply_text("❌ You are not in a chat.\n💬 Use /next to start chatting.")

# ─────────────  /me  ──────────────
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 🔒 Block-guard
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
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        if "language" not in u:
            buttons = [[InlineKeyboardButton(txt, callback_data=f'set_lang:{code}')] for code, txt in LANGUAGES.items()]
            await update.message.reply_text(
                "👇 Please select your language:\n🔸 You can change this later using /settings",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        return

    profile_text = get_profile(user_id)
    if user_id in active_chats:
        await update.message.reply_text(
            profile_text +
            "\n\n🔎 You are currently in a chat.\n💬 Use /stop to end or /next to skip."
        )
    else:
        await update.message.reply_text(
            profile_text +
            "\n\n💬 Use /next to find a new partner."
        )

# ─────────────  /settings  ──────────────
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settings command – shows Age / Language menu only if profile complete."""
    user_id = update.effective_user.id

    # 🔒 Block-guard 
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await update.message.reply_text(msg)
        return

    # make sure user-dict exists
    if user_id not in users:
        users[user_id] = {}
    u = users[user_id]

    # ── profile-completion guard ──
    if not is_profile_complete(user_id):
        await update.message.reply_text("🚫 Please complete your profile first.")

        # ask gender if missing
        if "gender" not in u:
            buttons = [[
                InlineKeyboardButton("🚹 Male",   callback_data="set_gender:Male"),
                InlineKeyboardButton("🚺 Female", callback_data="set_gender:Female"),
                InlineKeyboardButton("⚧ Other",  callback_data="set_gender:Other"),
            ]]
            await update.message.reply_text(
                "👇 Please select your gender. ⚠️ Once set, cannot be changed.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # ask language if missing
        if "language" not in u:
            buttons = [[InlineKeyboardButton(txt, callback_data=f"set_lang:{code}")]
                       for code, txt in LANGUAGES.items()]
            await update.message.reply_text(
                "👇 Please select your language:\n🔸 You can change this later using /settings",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        return  # should never reach here, but safety

    # ── profile complete → show settings menu ──
    menu_btns = [
    [InlineKeyboardButton("🎂 Age", callback_data="set_age")],
    [InlineKeyboardButton("🌐 Language", callback_data="change_language")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")]
]
    await update.message.reply_text("⚙️ Settings:", reply_markup=InlineKeyboardMarkup(menu_btns))


# ───────────  settings-callback (Age / Language lists) ───────────
async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # 🔒 Block-guard (✅ only blocks users if needed)
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await query.answer()
        await query.message.reply_text(msg)
        return

    await query.answer()  # ✅ spinner close for normal users

    # 👇 Age selection
    if query.data == "set_age":
        age_buttons = [
            [InlineKeyboardButton(str(a), callback_data=f"age:{a}") for a in range(i, i + 5)]
            for i in range(10, 84, 5)
        ]
        age_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")])
        await query.edit_message_text("🎂 Select your age:", reply_markup=InlineKeyboardMarkup(age_buttons))
        return AGE

    # 👇 Language selection
    if query.data == "change_language":
        lang_buttons = [[InlineKeyboardButton(txt, callback_data=f"set_lang:{code}")]
                        for code, txt in LANGUAGES.items()]
        lang_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")])
        await query.edit_message_text("🌐 Select your language:", reply_markup=InlineKeyboardMarkup(lang_buttons))
        return TYPING_LANGUAGE


# ───────────  set_age  ───────────
async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # 🔒 Block-guard 
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await query.message.reply_text(msg)
        return

    await query.answer()

    age = int(query.data.split(":")[1])
    users[user_id]["age"] = age
    await query.edit_message_text(f"🎂 Age updated to: {age}")


    # context-sensitive reply
    if user_id in active_chats:
        await query.message.reply_text(
            "💬 You are still in a chat.\n💬 Use /stop to end or /next to find a new partner."
        )
    else:
        await query.message.reply_text("💬 Use /next to start chatting.")
    return ConversationHandler.END


# ───────────  cancel_settings  ───────────
async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # 🔒 Block-guard (✅ corrected)
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


# ─────────────── Message Handler ──────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Block check
    is_blk, msg = is_currently_blocked(user_id)
    if is_blk:
        await update.message.reply_text(msg)
        return

    # Ensure user dict
    if user_id not in users:
        users[user_id] = {}
    u = users[user_id]

    # 🚫 Profile Incomplete
    if not is_profile_complete(user_id):
            await update.message.reply_text("🚫 Please complete your profile first.")
            if "gender" not in u:
                buttons = [[
                    InlineKeyboardButton("🚹 Male",   callback_data="set_gender:Male"),
                    InlineKeyboardButton("🚺 Female", callback_data="set_gender:Female"),
                    InlineKeyboardButton("⚧ Other",  callback_data="set_gender:Other"),
                ]]
                await update.message.reply_text("👇 Please select your gender. ⚠️ Once set, cannot be changed.",
                                                reply_markup=InlineKeyboardMarkup(buttons))
                return
            if "language" not in u:
                buttons = [[InlineKeyboardButton(txt, callback_data=f'set_lang:{code}')]
                           for code, txt in LANGUAGES.items()]
                await update.message.reply_text(
                    "👇 Please select your language:\n🔸 You can change this later using /settings",
                    reply_markup=InlineKeyboardMarkup(buttons))
                return
            return

    # ✅ If in chat
    if user_id in active_chats:
        partner_id = active_chats[user_id]

        msg = update.message

        # Text
        if msg.text:
            await context.bot.send_message(partner_id, msg.text)

        # Photo
        elif msg.photo:
            await context.bot.send_photo(partner_id, photo=msg.photo[-1].file_id, caption=msg.caption)

        # Sticker
        elif msg.sticker:
            await context.bot.send_sticker(partner_id, sticker=msg.sticker.file_id)

        # Voice
        elif msg.voice:
            await context.bot.send_voice(partner_id, voice=msg.voice.file_id)

        # Video
        elif msg.video:
            await context.bot.send_video(partner_id, video=msg.video.file_id, caption=msg.caption)

        # GIF (animation)
        elif msg.animation:
            await context.bot.send_animation(partner_id, animation=msg.animation.file_id, caption=msg.caption)

        # Audio
        elif msg.audio:
            await context.bot.send_audio(partner_id, audio=msg.audio.file_id, caption=msg.caption)

        # Document
        elif msg.document:
            await context.bot.send_document(partner_id, document=msg.document.file_id, caption=msg.caption)

    # ✅ Profile complete but NOT in chat
    elif user_id in waiting_users:
        await update.message.reply_text(
        "⏳ Searching for a partner…\n"
        "❌ You are not in a chat yet.\n"
        "💤 To stop searching, use /stop."
    )
    else:
        await update.message.reply_text("❌ You are not in a chat.\n💬 Use /next to find a partner.")

# ────────────────  Report system  ────────────────
REPORT_REASONS = {
    "Advertising": "📢 Advertising",
    "Selling":     "💰 Selling",
    "Child":       "🚫 Child Porn",
    "Begging":     "🙏 Begging",
    "Insult":      "😡 Insulting",
    "Violence":    "⚔️ Violence",
    "Vulgar":      "🤬 Vulgar Partner"
}

# 🔸 “🚩 Report” बटन ⇢ यह मेनू खोलता है
async def open_report_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # stop/next पर स्टोर किया गया पिछला partner
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

# 🔸 reason या “Cancel” क्लिक होने पर
async def handle_report_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Cancel → मेसेज हटा कर लौटो
    if query.data == "rep_cancel":
        await query.edit_message_text("❌ Report cancelled.\n💬 Use /next to start chatting.")
        return

    reason_key = query.data.split(":")[1]
    reason_txt = REPORT_REASONS[reason_key]

    partner_id = context.user_data.pop("last_partner", None)

    # Reporter को confirmation
    await query.edit_message_text(
        "✅ Report submitted. Thank you!\n💬 Use /next to start chatting."
    )

    # Admins को सूचना
    for admin in admins:
        await context.bot.send_message(
            admin,
            f"🚨 Report Received\nReporter: {user_id}\nAgainst: {partner_id}\nReason: {reason_txt}"
        )

    # History में दर्ज
    report_history.append({
        "reporter": user_id,
        "reported": partner_id,
        "reason": reason_txt,
        "time": datetime.utcnow(),
        "handled": False
    })
# ──────────────────────────────────────────────────

# ────────────────────────────────────────────────
#  ADMIN & MODERATION SECTION  (replace old block)
# ────────────────────────────────────────────────
from datetime import datetime, timedelta

# per-user block-info:  {uid: {"until": datetime , "count": n , "reason": str}}
blocked_users: dict[int, dict] = {}

# helper – check if a user is blocked right now
def is_currently_blocked(uid: int) -> tuple[bool, str | None]:
    info = blocked_users.get(uid)
    if not info:
        return False, None

    if datetime.utcnow() < info["until"]:
        # Block अभी active है
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

    return False, None  # Block expire हो गया

# escalation table (in hours)
BLOCK_STEPS = [24, 48, 96, 480, 720]           # 1d,2d,4d,20d,30d

# ─────────────  ADMIN PANEL  ─────────────
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the root admin panel (only for admins)."""
    if update.effective_user.id not in admins:
        return            # non-admin → ignore, fallback handled elsewhere

    root_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Reports",       callback_data="admin:reports")],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="admin:blocked")],
        [InlineKeyboardButton("📊 Stats",         callback_data="admin:stats")],
    ])
    await update.effective_message.reply_text(
        "🛡 *Admin Panel*", reply_markup=root_buttons, parse_mode="Markdown"
    )


# ─────────────  ADMIN CALLBACKS  ─────────────
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """All inline-button clicks that start with admin:, rep_filter:, rep_info:, blk_ …"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if uid not in admins:
        return

    data = query.data

    # === root-level back (comes from any sub-menu) ==============
    if data == "admin:back":
        # delete current inline message & send fresh root panel
        try:
            await query.message.delete()
        except Exception:
            pass
        await admin(update, context)      # show root again
        return
    from asyncio import sleep

async def unblock_expired_users(bot):
    while True:
        now = datetime.utcnow()
        to_unblock = []

        for uid, info in blocked_users.items():
            if now >= info["until"]:
                to_unblock.append(uid)

        for uid in to_unblock:
            blocked_users.pop(uid, None)
            try:
                await bot.send_message(
                    uid,
                    "✅ Your ban has expired. You can now use the chat again.\nUse /start to begin."
                )
            except:
                pass

        await sleep(60)  # Check every 1 minute


    # ====  REPORTS root menu  ==================================
    if data == "admin:reports":
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 All open",    callback_data="rep_filter:all")],
            [InlineKeyboardButton("🗓 Last 7 days", callback_data="rep_filter:7d")],
            [InlineKeyboardButton("⚠️ 3+ reports",  callback_data="rep_filter:3+")],
            [InlineKeyboardButton("🔙 Back",        callback_data="admin:back")],
        ])
        await query.edit_message_text(
            "📋 *Open Reports* – choose filter:",
            reply_markup=buttons, parse_mode="Markdown"
        )
        return

    # ====  BLOCKED users list  =================================
    if data == "admin:blocked":
        if not blocked_users:
            await query.edit_message_text(
                "✅ No users are currently blocked.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:back")]])
            )
            return

        rows = []
        for uid_, info in blocked_users.items():
            hrs_left = int((info["until"] - datetime.utcnow()).total_seconds() // 3600)
            rows.append(
                [InlineKeyboardButton(f"{uid_} ({hrs_left}h)", callback_data=f"blk_info:{uid_}")]
            )
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

        await query.edit_message_text(
            "🚫 *Blocked Users* (UID – hours left):",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )
        return

    # ====  STATS  ==============================================
    if data == "admin:stats":
        total_users   = len(users)
        profiles_done = sum(1 for u in users.values() if is_profile_complete_dict(u))
        active        = len(active_chats) // 2
        searching     = len(waiting_users)
        new_today     = sum(1 for u in users.values()
                            if u.get('created') == datetime.utcnow().date().isoformat())
        online        = len({*active_chats.keys(), *waiting_users})
        blocked_cnt   = len(blocked_users)
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
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:back")]])
        )
        return

    # ========== REPORT FILTER HANDLING =========================
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
            await query.edit_message_text(
                "🎉 No reports in this filter.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:reports")]])
            )
            return

        rows = [[InlineKeyboardButton(str(r["reported"]), callback_data=f"rep_info:{r['reported']}")]
                for r in open_reports[:50]]
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin:reports")])

        await query.edit_message_text(
            "📋 *Select a user to review:*",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown"
        )
        return

    # ========== REPORT DETAILS  ================================
    if data.startswith("rep_info:"):
        rid = int(data.split(":")[1])
        user_reports = [r for r in report_history if r["reported"] == rid]
        total  = len(user_reports)
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
            parse_mode="Markdown", reply_markup=btns
        )
        return

    # ========== BLOCK-INFO  ====================================
    if data.startswith("blk_info:"):
        rid  = int(data.split(":")[1])
        info = blocked_users[rid]
        hrs_left = int((info["until"] - datetime.utcnow()).total_seconds() // 3600)

        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Unblock", callback_data=f"blk_un:{rid}")],
            [InlineKeyboardButton("🔙 Back",   callback_data="admin:blocked")]
        ])
        await query.edit_message_text(
            f"🚫 *Blocked user* `{rid}`\n"
            f"Reason : {info['reason']}\n"
            f"Times  : {info['count']}\n"
            f"Ends   : {info['until'].strftime('%Y-%m-%d %H:%M')} ({hrs_left}h left)",
            parse_mode="Markdown", reply_markup=btns
        )
        return

    # ========== EXECUTE BLOCK  =================================
    if data.startswith("blk_do:"):
        rid = int(data.split(":")[1])
        cnt = blocked_users.get(rid, {}).get("count", 0)
        hours = BLOCK_STEPS[min(cnt, len(BLOCK_STEPS) - 1)]
        until = datetime.utcnow() + timedelta(hours=hours)
        blocked_users[rid] = {"until": until, "count": cnt + 1, "reason": "Admin"}

        # mark their open reports handled
        for r in report_history:
            if r["reported"] == rid and not r["handled"]:
                r["handled"] = True

        await query.edit_message_text(
            f"🚫 User `{rid}` blocked for {hours} hours.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:reports")]])
        )
        return

# ========== UNBLOCK (Manual by Admin) ======================
if data.startswith("blk_un:"):
    rid = int(data.split(":")[1])
    blocked_users.pop(rid, None)

    await query.edit_message_text(
        f"✅ User `{rid}` unblocked.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin:blocked")]])
    )

    # 🔔 Notify user
    try:
        await context.bot.send_message(
            rid,
            "✅ You have been unblocked and can now use the chat again.\nUse /start to begin."
        )
    except:
        pass  # Bot can't reach user
    return

# ─────────────  BLOCK-CHECK AT START  ─────────────
def is_profile_complete_dict(d: dict) -> bool:
    return "gender" in d and "language" in d

# (यह छोटा check ज़रूरत अनुसार /start और message_handler की शुरुआत में जोड़ें)
# is_blk, msg = is_currently_blocked(user_id)
# if is_blk:
#     await update.message.reply_text(msg)
#     return ConversationHandler.END


# ─────────────  CONVERSATION HANDLERS  ─────────────
# (ये दो blocks पहले से न हों तो इसी MAIN से ऊपर रख दें)

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        GENDER:    [CallbackQueryHandler(set_gender, pattern="^set_gender:")],
        LANGUAGE:  [CallbackQueryHandler(set_language_initial, pattern="^set_lang:")]
    },
    fallbacks=[],
    allow_reentry=True,
)

settings_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(setting_callback, pattern="^(set_age|change_language)$")],
    states={
        AGE:              [CallbackQueryHandler(set_age, pattern="^age:")],
        TYPING_LANGUAGE: [CallbackQueryHandler(set_language_change, pattern="^set_lang:")]
    },
    fallbacks=[CallbackQueryHandler(cancel_settings, pattern="^cancel_settings$")],
)

if __name__ == "__main__":
    import os
    from telegram.ext import ApplicationBuilder, filters
    from flask import Flask
    from threading import Thread

    TOKEN = os.getenv("BOT_TOKEN")

    # --- Telegram Bot Setup ---
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # Handlers setup
    app.add_handler(conv)
    app.add_handler(settings_conv)
    app.add_handler(CallbackQueryHandler(cancel_settings, pattern="^cancel_settings$"))

    app.add_handler(CommandHandler("next",     next_command))
    app.add_handler(CommandHandler("stop",     stop_command))
    app.add_handler(CommandHandler("me",       me))
    app.add_handler(CommandHandler("settings", settings))

    app.add_handler(CallbackQueryHandler(open_report_menu,     pattern="^report:open$"))
    app.add_handler(CallbackQueryHandler(handle_report_reason, pattern="^rep_reason:"))
    app.add_handler(CallbackQueryHandler(handle_report_reason, pattern="^rep_cancel$"))

    app.add_handler(CommandHandler("admin", admin, filters=filters.User(admins)))
    app.add_handler(CallbackQueryHandler(admin_callback,
                                         pattern="^(admin:|rep_filter:|rep_info:|blk_).*"))

    app.add_handler(MessageHandler(filters.ALL, message_handler))

    print("✅ Gabbar Chat is starting...")

    # --- Flask Server in Background ---
    flask_app = Flask(__name__)

    @flask_app.route('/')
    def home():
        return "✅ Bot is alive!"

    def run_flask():
        flask_app.run(host='0.0.0.0', port=8080)

    Thread(target=run_flask).start()
    import asyncio
asyncio.get_event_loop().create_task(unblock_expired_users(app.bot))


    # --- Telegram Bot in Main Thread ---
    app.run_polling()
