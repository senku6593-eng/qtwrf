import csv
import os
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, ADMINS, CHANNELS, CHANNEL_IDS

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


def ticket_keyboard(ticket_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ticket_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_{ticket_id}")
        ]
    ])


def rating_keyboard(ticket_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_1_{ticket_id}"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_2_{ticket_id}"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_3_{ticket_id}"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_4_{ticket_id}"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_5_{ticket_id}")
        ]
    ])


def new_ticket_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Подать заявку", callback_data="new_ticket")]
    ])


# ================= WELCOME =================
async def send_welcome(obj):
    text = (
        f"🎄✨ Привет, @{obj.from_user.username}! ✨🎄\n\n"
        "❄️ Бот поможет с Трейд-скриптами Standoff 2.\n"
        "💡 Можно задать любой вопрос, и мы постараемся помочь!\n\n"
        "🎁 Хотите продолжить? Создайте новую заявку 👇"
    )
    kb = new_ticket_kb()

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

    # объединяем дополнительный текст
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
            call.from_user.username,
            ticket_id,
            data["text"],
            data.get("media_type") or "",
            data.get("media_id") or "",
            "No"
        ])

    # уведомляем админов
    for admin in ADMINS:
        kb = ticket_keyboard(ticket_id)
        msg_text = f"🎟 Новая заявка\n\n👤 @{call.from_user.username}\n🎫 Ticket #{ticket_id}\n\n💬 {data['text']}"
        if data.get("media_type") == "photo":
            await bot.send_photo(admin, photo=data["media_id"], caption=msg_text, reply_markup=kb)
        elif data.get("media_type") == "video":
            await bot.send_video(admin, video=data["media_id"], caption=msg_text, reply_markup=kb)
        else:
            await bot.send_message(admin, msg_text, reply_markup=kb, parse_mode="Markdown")

    await call.message.answer("✅ Сообщение успешно отправлено! Ожидайте ответа Администрации.")
    await send_welcome(call)
    await state.clear()


# ================= ADMIN APPROVE =================
@dp.callback_query(F.data.startswith("approve_"))
async def approve(call: CallbackQuery, state: FSMContext):
    ticket_id = int(call.data.split("_")[1])
    await state.set_state(TicketState.admin_reply)
    await state.update_data(ticket=ticket_id)
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

    text = f"🎉 **Администратор ответил!**\n\n💌 Сообщение:\n{message.text or message.caption}\n\n🎫 Ticket #{ticket_id} закрыт! 🌟"
    try:
        if media_type == "photo":
            await bot.send_photo(user_id, photo=media_id, caption=text, parse_mode="Markdown")
        elif media_type == "video":
            await bot.send_video(user_id, video=media_id, caption=text, parse_mode="Markdown")
        else:
            await bot.send_message(user_id, text, parse_mode="Markdown")

        await bot.send_message(user_id, "⭐ Оставьте оценку", reply_markup=rating_keyboard(ticket_id))
    except TelegramBadRequest:
        await message.answer("❌ Не удалось отправить сообщение пользователю.")

    await message.answer(f"✅ Ticket #{ticket_id} закрыт")
    await send_welcome(message)
    await state.clear()


# ================= ADMIN DENY =================
@dp.callback_query(F.data.startswith("deny_"))
async def deny_ticket(call: CallbackQuery):
    ticket_id = int(call.data.split("_")[1])
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

    try:
        await bot.send_message(
            user_id,
            f"❌ Ваша заявка отклонена\n🎫 Ticket #{ticket_id}\nЕсли есть другие вопросы — создайте новую заявку 🎄",
            reply_markup=new_ticket_kb()
        )
    except TelegramBadRequest:
        pass

    await call.message.edit_text(f"❌ Заявка Ticket #{ticket_id} отклонена", parse_mode="Markdown")
    await call.answer("Заявка отклонена")


# ================= RATING =================
@dp.callback_query(F.data.startswith("rate_"))
async def rate_ticket(call: CallbackQuery):
    _, stars, ticket_id = call.data.split("_")

    with open(RATING_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([call.from_user.username, stars, ticket_id])

    for admin in ADMINS:
        await bot.send_message(admin, f"⭐ Пользователь @{call.from_user.username} оценил Ticket #{ticket_id} на {stars}⭐")

    await call.message.answer("🎄 Спасибо за оценку! С Новым Годом! 🎉")


# ================= RUN =================
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
