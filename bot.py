import csv
import os
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, ADMINS, CHANNELS, CHANNEL_IDS
from gold import register_gold_handlers  # подключаем файл с голдой

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

TICKET_FILE = "tickets.csv"
RATING_FILE = "ratings.csv"
SUBSCRIBED_FILE = "subscribed.csv"

# ================= STATES =================
class TicketState(StatesGroup):
    waiting_message = State()
    add_more = State()
    admin_reply = State()

# ================= АНТИСПАМ / КУЛДАУН =================
user_cooldowns = {}  # key = f"{user_id}_{action}" -> datetime
ticket_taken_by = {}  # ticket_id -> admin_id (кто взял тикет)
rated_tickets = set()  # user_id_ticket -> уже оценил

async def check_cooldown(user_id: int, action: str, cooldown_seconds: int) -> bool:
    now = datetime.now()
    key = f"{user_id}_{action}"
    last = user_cooldowns.get(key)
    if last and (now - last).total_seconds() < cooldown_seconds:
        return False
    user_cooldowns[key] = now
    return True

# ================= UTILS =================
def get_next_ticket_id():
    if not os.path.exists(TICKET_FILE):
        return 1
    with open(TICKET_FILE, newline="", encoding="utf-8") as f:
        return sum(1 for _ in f) + 1

def is_user_subscribed(user_id: int) -> bool:
    if not os.path.exists(SUBSCRIBED_FILE):
        return False
    with open(SUBSCRIBED_FILE, newline="", encoding="utf-8") as f:
        return str(user_id) in [row[0] for row in csv.reader(f)]

def mark_user_subscribed(user_id: int):
    if not is_user_subscribed(user_id):
        with open(SUBSCRIBED_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([user_id])

async def check_subscriptions(user_id: int) -> bool:
    for chat_id in CHANNEL_IDS:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("left", "kicked"):
                return False
        except TelegramBadRequest:
            return False
        except Exception:
            return False
    return True

def ticket_keyboard(ticket_id: int):
    if ticket_id in ticket_taken_by:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Тикет уже взят", callback_data="already_taken")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ticket_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_{ticket_id}")
        ]
    ])

def rating_keyboard(ticket_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_1_{ticket_id}"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_2_{ticket_id}"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_3_{ticket_id}"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_4_{ticket_id}"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_5_{ticket_id}")
        ]
    ])

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Подать заявку", callback_data="new_ticket")],
        [InlineKeyboardButton(text="💰 Заработать голды", callback_data="earn_gold")]
    ])

# ================= WELCOME =================
async def send_welcome(obj):
    text = (
        f"🎄✨ Привет, @{obj.from_user.username}! ✨🎄\n\n"
        "❄️ Бот поможет с Трейд-скриптами Standoff 2.\n"
        "💡 Можно задать любой вопрос, и мы постараемся помочь!\n\n"
        "🎁 Хотите продолжить? Создайте новую заявку или заработайте голды 👇"
    )
    kb = main_menu_kb()
    if isinstance(obj, Message):
        await obj.answer(text, reply_markup=kb, parse_mode="Markdown")
    elif isinstance(obj, CallbackQuery):
        await obj.message.answer(text, reply_markup=kb, parse_mode="Markdown")

# ================= START =================
@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    if is_user_subscribed(user_id):
        await send_welcome(message)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎄 Wiazy Project", url=CHANNELS["Wiazy Project"])],
        [InlineKeyboardButton(text="🎄 Wiazy Chat", url=CHANNELS["Wiazy Chat"])],
        [InlineKeyboardButton(text="✅ Проверить подписки", callback_data="check_sub")]
    ])
    await message.answer(
        "🎄✨ С НОВЫМ ГОДОМ! ✨🎄\n\n"
        "Чтобы мы могли вам помочь — подпишитесь на каналы 👇\n"
        "🎁 После подписки нажмите кнопку проверки!",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# ================= CHECK SUB =================
@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if not await check_subscriptions(call.from_user.id):
        await call.answer("❌ Вы не подписаны на все каналы!", show_alert=True)
        return
    mark_user_subscribed(call.from_user.id)
    await send_welcome(call)

# ================= NEW TICKET =================
@dp.callback_query(F.data == "new_ticket")
async def new_ticket(call: CallbackQuery, state: FSMContext):
    if not await check_cooldown(call.from_user.id, "new_ticket", 60):
        await call.answer("🕒 Новую заявку можно отправлять раз в 1 минуту!", show_alert=True)
        return

    await state.set_state(TicketState.waiting_message)
    await state.update_data(text="", media_type=None, media_id=None)
    await call.message.answer(
        "📝 Опиши свою проблему.\n📎 Можно текст + фото / видео 🎄"
    )

@dp.message(TicketState.waiting_message, F.content_type.in_({"text", "photo", "video"}))
async def get_ticket_message(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text or message.caption or ""
    media_type = None
    media_id = None

    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id

    data["text"] = (data.get("text") or "") + ("\n" + text if data.get("text") else text)
    if media_type:
        data["media_type"] = media_type
        data["media_id"] = media_id

    await state.update_data(**data)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Хочу добавить ещё", callback_data="add_more"),
            InlineKeyboardButton(text="❌ Готово, отправить", callback_data="send_ticket")
        ]
    ])
    await state.set_state(TicketState.add_more)
    await message.answer("🎄 Хотите дополнить заявку?", reply_markup=kb)

@dp.callback_query(F.data == "add_more")
async def add_more(call: CallbackQuery, state: FSMContext):
    await state.set_state(TicketState.waiting_message)
    await call.message.answer("➕ Отправьте дополнительное сообщение")

@dp.callback_query(F.data == "send_ticket")
async def send_ticket(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ticket_id = get_next_ticket_id()

    with open(TICKET_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            call.from_user.id,
            call.from_user.username or "",
            ticket_id,
            data["text"],
            data.get("media_type") or "",
            data.get("media_id") or "",
            "No",  # статус
            ""     # admin_id
        ])

    for admin in ADMINS:
        kb = ticket_keyboard(ticket_id)
        msg_text = (
            f"🎟 Новая заявка\n\n"
            f"👤 @{call.from_user.username}\n"
            f"🎫 Ticket #{ticket_id}\n\n"
            f"💬 {data['text']}"
        )
        if data.get("media_type") == "photo":
            await bot.send_photo(admin, photo=data["media_id"], caption=msg_text, reply_markup=kb)
        elif data.get("media_type") == "video":
            await bot.send_video(admin, video=data["media_id"], caption=msg_text, reply_markup=kb)
        else:
            await bot.send_message(admin, msg_text, reply_markup=kb, parse_mode="Markdown")

    await call.message.answer("✅ Сообщение успешно отправлено! Ожидайте ответа Администрации.")
    await send_welcome(call)
    await state.clear()

# ================= ADMIN APPROVE / DENY =================
@dp.callback_query(F.data == "already_taken")
async def already_taken(call: CallbackQuery):
    await call.answer("Этот тикет уже взят другим админом. 🎄", show_alert=True)

@dp.callback_query(F.data.startswith("approve_"))
async def approve(call: CallbackQuery, state: FSMContext):
    ticket_id = int(call.data.split("_")[1])
    if ticket_id in ticket_taken_by and ticket_taken_by[ticket_id] != call.from_user.id:
        await call.answer("Этот тикет уже взят другим админом.", show_alert=True)
        return

    ticket_taken_by[ticket_id] = call.from_user.id
    admin_id = str(call.from_user.id)

    # НАЙДИ И ОБНОВИ ТОЧНУЮ СТРОКУ tickets.csv
    rows = []
    found = False
    with open(TICKET_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    for row in rows:
        if len(row) >= 3 and str(row[2]) == str(ticket_id):
            # Обеспечиваем 8 колонок
            while len(row) < 8:
                row.append("")
            row[7] = admin_id  # 8-я колонка = admin_id
            found = True
            break

    if not found:
        await call.answer("❌ Ошибка: тикет не найден!", show_alert=True)
        return

    with open(TICKET_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    # уведомление всем админам
    for admin in ADMINS:
        try:
            await bot.send_message(admin, f"🎄 Тикет #{ticket_id} взял админ: {admin_id}")
        except:
            pass

    await state.set_state(TicketState.admin_reply)
    await state.update_data(ticket=ticket_id)
    await call.message.edit_reply_markup(reply_markup=ticket_keyboard(ticket_id))
    await call.message.answer("✍️ Отправьте ответ пользователю (текст + медиа)")

@dp.message(TicketState.admin_reply, F.content_type.in_({"text", "photo", "video"}))
async def admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = int(data["ticket"])

    # ищем пользователя по ticket_id
    user_id = None
    with open(TICKET_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        for row in rows:
            if len(row) >= 3 and str(row[2]) == str(ticket_id):
                user_id = int(row[0])
                break

    if not user_id:
        await message.answer("❌ Пользователь для этого тикета не найден.")
        await state.clear()
        return

    media_type = None
    media_id = None
    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id

    text = (
        "🎉 **Администратор ответил!**\n\n"
        f"💌 Сообщение:\n{message.text or message.caption}\n\n"
        f"🎫 Ticket #{ticket_id} закрыт! 🌟\n\n"
        "⭐ Оставьте оценку за этот тикет:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_1_{ticket_id}"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_2_{ticket_id}"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_3_{ticket_id}"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_4_{ticket_id}"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_5_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="🎟 Подать заявку", callback_data="new_ticket"),
            InlineKeyboardButton(text="💰 Заработать голды", callback_data="earn_gold")
        ]
    ])

    try:
        if media_type == "photo":
            await bot.send_photo(user_id, photo=media_id, caption=text, reply_markup=kb, parse_mode="Markdown")
        elif media_type == "video":
            await bot.send_video(user_id, video=media_id, caption=text, reply_markup=kb, parse_mode="Markdown")
        else:
            await bot.send_message(user_id, text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest:
        await message.answer("❌ Не удалось отправить сообщение пользователю.")

    await send_welcome(message)
    await state.clear()

@dp.callback_query(F.data.startswith("deny_"))
async def deny_ticket(call: CallbackQuery):
    ticket_id = int(call.data.split("_")[1])

    if ticket_id in ticket_taken_by and ticket_taken_by[ticket_id] != call.from_user.id:
        await call.answer("Этот тикет уже взят другим админом.", show_alert=True)
        return

    ticket_taken_by[ticket_id] = call.from_user.id

    user_id = None
    with open(TICKET_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
        for row in rows:
            if len(row) >= 3 and str(row[2]) == str(ticket_id):
                user_id = int(row[0])
                break

    if not user_id:
        await call.answer("❌ Пользователь для этого тикета не найден.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎟 Подать заявку", callback_data="new_ticket"),
            InlineKeyboardButton(text="💰 Заработать голды", callback_data="earn_gold")
        ]
    ])

    try:
        await bot.send_message(
            user_id,
            f"❌ Ваша заявка отклонена\n🎫 Ticket #{ticket_id}\nЕсли есть другие вопросы — создайте новую заявку 🎄",
            reply_markup=kb
        )
    except TelegramBadRequest:
        pass

    await call.message.edit_text(f"❌ Заявка Ticket #{ticket_id} отклонена", parse_mode="Markdown")
    await call.answer("Заявка отклонена")

# ================= RATING / РЕЙТИНГ АДМИНОВ =================
@dp.callback_query(F.data.startswith("rate_"))
async def rate_ticket(call: CallbackQuery):
    _, stars, ticket_id = call.data.split("_")
    key = f"{call.from_user.id}_{ticket_id}"
    if key in rated_tickets:
        await call.answer("Вы уже оценили этот тикет. ⭐", show_alert=True)
        return
    rated_tickets.add(key)

    # НАХОДИМ ТОЧНЫЙ ADMIN_ID из tickets.csv (8-я колонка)
    admin_id = None
    with open(TICKET_FILE, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if (len(row) >= 8 and 
                str(row[2]) == str(ticket_id) and 
                row[7] and row[7].isdigit()):
                admin_id = row[7]
                break

    if not admin_id:
        await call.answer("❌ Ошибка: админ не назначен этому тикету!", show_alert=True)
        return

    # СОХРАНЯЕМ: username, stars, REAL_ADMIN_ID
    with open(RATING_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([call.from_user.username or "", stars, admin_id])

    for admin in ADMINS:
        await bot.send_message(
            admin,
            f"⭐ Пользователь @{call.from_user.username or 'Без имени'} оценил тикет #{ticket_id} на {stars}⭐\n"
            f"👤 Админ: `{admin_id}`"
        )

    await call.message.edit_text("🎄 Спасибо за вашу оценку! С Новым Годом! 🎉")

def calculate_admin_rating():
    """Считает средний рейтинг для каждого админа"""
    if not os.path.exists(RATING_FILE):
        return {}

    ratings = {}
    with open(RATING_FILE, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            stars = int(row[1])
            admin_id = row[2]
            if admin_id and admin_id.isdigit():
                if admin_id not in ratings:
                    ratings[admin_id] = []
                ratings[admin_id].append(stars)

    result = {}
    for admin_id, stars_list in ratings.items():
        avg = sum(stars_list) / len(stars_list)
        result[admin_id] = {
            "rating": round(avg, 1),
            "count": len(stars_list)
        }
    return result

@dp.message(Command("rating"))
async def show_rating(message: Message):
    if message.from_user.id not in ADMINS:
        return
    
    ratings = calculate_admin_rating()
    if not ratings:
        await message.answer("Пока нет оценок. ❄️")
        return

    sorted_ratings = sorted(ratings.items(), key=lambda x: x[1]["rating"], reverse=True)
    text = "🏆 *Топ админов по рейтингу:*\n\n"
    for i, (admin_id, data) in enumerate(sorted_ratings, 1):
        text += f"{i}. 👑 `{admin_id}` — {data['rating']}⭐ ({data['count']} оценок)\n"
    
    text += f"\n*Всего админов: {len(ratings)}*"
    await message.answer(text, parse_mode="Markdown")

# ================= GOLD HANDLERS =================
register_gold_handlers(dp, bot)

# ================= RUN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
