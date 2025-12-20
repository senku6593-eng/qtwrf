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
from config import BOT_TOKEN, ADMINS, CHANNELS, CHANNEL_IDS  # ✅ Исправлено
from gold import registergoldhandlers

bot = Bot(BOT_TOKEN)  # ✅ BOT_TOKEN вместо BOTTOKEN
dp = Dispatcher()

TICKETFILE = "tickets.csv"
RATINGFILE = "ratings.csv"
SUBSCRIBEDFILE = "subscribed.csv"

class TicketState(StatesGroup):
    waiting_message = State()
    addmore = State()
    adminreply = State()

usercooldowns = {}  # key: f"{userid}_{action}" -> datetime
tickettakenby = {}  # ticketid -> adminid
ratedtickets = set()  # userid_ticket

async def checkcooldown(userid: int, action: str, cooldownseconds: int) -> bool:
    now = datetime.now()
    key = f"{userid}_{action}"
    last = usercooldowns.get(key)
    if last and (now - last).total_seconds() < cooldownseconds:
        return False
    usercooldowns[key] = now
    return True

def getnextticketid():
    if not os.path.exists(TICKETFILE):
        return 1
    with open(TICKETFILE, 'r', newline='', encoding='utf-8') as f:
        return sum(1 for _ in f) + 1

def isusersubscribed(userid: int) -> bool:
    if not os.path.exists(SUBSCRIBEDFILE):
        return False
    with open(SUBSCRIBEDFILE, 'r', newline='', encoding='utf-8') as f:
        return str(userid) in [row[0] for row in csv.reader(f)]

def markusersubscribed(userid: int, username: str):
    if not isusersubscribed(userid):
        with open(SUBSCRIBEDFILE, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([userid, username or ""])

async def checksubscriptions(userid: int) -> bool:
    for chatid in CHANNEL_IDS:  # ✅ CHANNEL_IDS
        try:
            member = await bot.get_chat_member(chatid, userid)
            if member.status in ['left', 'kicked']:
                return False
        except TelegramBadRequest:
            return False
        except Exception:
            return False
    return True

def ticketkeyboard(ticketid: int):
    if ticketid in tickettakenby:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Уже взято", callback_data="alreadytaken")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять", callback_data=f"approve_{ticketid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_{ticketid}")]
    ])

def ratingkeyboard(ticketid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐", callback_data=f"rate_1_{ticketid}"),
         InlineKeyboardButton(text="⭐⭐", callback_data=f"rate_2_{ticketid}"),
         InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate_3_{ticketid}")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate_4_{ticketid}"),
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate_5_{ticketid}")]
    ])

def mainmenukb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Новый тикет", callback_data="newticket"),
         InlineKeyboardButton(text="💰 Заработать голду", callback_data="earngold")]
    ])

async def sendwelcome(obj, targetuserid: int = None, targetusername: str = None):
    try:
        if targetuserid:
            user = await bot.get_chat(targetuserid)
            username = user.username or targetusername or f"user{targetuserid}"
        else:
            username = obj.from_user.username or f"user{obj.from_user.id}"
    except:
        username = targetusername or f"user{obj.from_user.id}"
    
    markusersubscribed(obj.from_user.id if not targetuserid else targetuserid, username)
    
    text = (
        f"🎄 <b>❄️ С НОВЫМ ГОДОМ, @{username} ! ❄️</b> 🎅\n\n"
        f"🎁 <b>Добро пожаловать в Новогоднюю поддержку Standoff 2!</b>\n\n"
        f"🎀 Wiazy Project поздравляет с праздником! 🎀\n\n"
        f"❓ <b>Чем можем помочь в этот волшебный день?</b>\n\n"
        f"🎄 <b>Тикеты • Голда • Поддержка 24/7</b> 🎁"
    )
    kb = mainmenukb()
    
    try:
        if targetuserid:
            await bot.send_message(targetuserid, text, reply_markup=kb, parse_mode="HTML")
        elif isinstance(obj, Message):
            await obj.answer(text, reply_markup=kb, parse_mode="HTML")
        elif isinstance(obj, CallbackQuery):
            await obj.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        if not targetuserid:
            await obj.answer(
                "🎅 <b>С Новым годом! ❄️</b>\n\n"
                "🎄 Подпишись на каналы поддержки Standoff 2! 🎁",
                reply_markup=kb, parse_mode="HTML"
            )


@dp.message(Command("clen"))
async def clencommand(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("clen <userid>", parse_mode="Markdown")
        return
    
    try:
        targetuserid = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный ID пользователя!")
        return
    
    await sendwelcome(message, targetuserid=targetuserid, targetusername="")
    await message.answer(f"✅ {targetuserid}!\n✅ Добавлен в subscribed.csv\n📨 Отправлено welcome-сообщение.", parse_mode="Markdown")

@dp.message(Command("start"))
async def startmessage(message: Message):
    userid = message.from_user.id
    if isusersubscribed(userid):
        await sendwelcome(message)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Wiazy Project", url=CHANNELS["Wiazy Project"]),
         InlineKeyboardButton(text="Wiazy Chat", url=CHANNELS["Wiazy Chat"])],
        [InlineKeyboardButton(text="✅ Проверить", callback_data="checksub")]
    ])
    await message.answer("❄️ Подпишись на каналы поддержки!\n\n✅ После подписки нажми «Проверить»", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "checksub")
async def checksubcall(call: CallbackQuery):
    if not await checksubscriptions(call.from_user.id):
        await call.answer("❌ Не подписан на все каналы!", show_alert=True)
        return
    markusersubscribed(call.from_user.id, call.from_user.username or "")
    await sendwelcome(call)

@dp.callback_query(F.data == "newticket")
async def newticketcall(call: CallbackQuery, state: FSMContext):
    if not await checkcooldown(call.from_user.id, "newticket", 60):
        await call.answer("⏱️ 1 минута между тикетами!", show_alert=True)
        return
    await state.set_state(TicketState.waiting_message)
    await state.update_data(text="", mediatype=None, mediaid=None)
    await call.message.answer("📩 Напиши свою проблему:")

@dp.message(TicketState.waiting_message, F.content_type.in_({"text", "photo", "video"}))
async def getticketmessage(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text or message.caption or ""
    mediatype = None
    mediaid = None
    if message.photo:
        mediatype = "photo"
        mediaid = message.photo[-1].file_id
    elif message.video:
        mediatype = "video"
        mediaid = message.video.file_id
    
    data["text"] = data.get("text", "") + text if data.get("text") else text
    if mediatype:
        data["mediatype"] = mediatype
        data["mediaid"] = mediaid
    await state.update_data(data)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="addmore"),
         InlineKeyboardButton(text="✅ Отправить", callback_data="sendticket")]
    ])
    await state.set_state(TicketState.addmore)
    await message.answer("✅ Отлично! Добавить еще?", reply_markup=kb)

@dp.callback_query(F.data == "addmore")
async def addmorecall(call: CallbackQuery, state: FSMContext):
    await state.set_state(TicketState.waiting_message)
    await call.message.answer("➕ Добавь еще информацию:")

@dp.callback_query(F.data == "sendticket")
async def sendticketcall(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ticketid = getnextticketid()
    
    with open(TICKETFILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            call.from_user.id, call.from_user.username or "", ticketid, data["text"],
            data.get("mediatype", ""), data.get("mediaid", ""), "No", ""
        ])
    
    for admin in ADMINS:
        kb = ticketkeyboard(ticketid)
        msgtext = f"👤 {call.from_user.username}\n📊 Ticket #{ticketid}\n\n{data['text']}"
        if data.get("mediatype") == "photo":
            await bot.send_photo(admin, photo=data["mediaid"], caption=msgtext, reply_markup=kb)
        elif data.get("mediatype") == "video":
            await bot.send_video(admin, video=data["mediaid"], caption=msgtext, reply_markup=kb)
        else:
            await bot.send_message(admin, msgtext, reply_markup=kb, parse_mode="Markdown")
    
    await call.message.answer("✅ Тикет отправлен!")
    await sendwelcome(call)
    await state.clear()

@dp.callback_query(F.data == "alreadytaken")
async def alreadytakencall(call: CallbackQuery):
    await call.answer("✅ Тикет уже взят другим админом!", show_alert=True)

@dp.callback_query(F.data.startswith("approve_"))
async def approvecall(call: CallbackQuery, state: FSMContext):
    ticketid = int(call.data.split("_")[1])
    if ticketid in tickettakenby and tickettakenby[ticketid] != call.from_user.id:
        await call.answer("❌ Тикет уже взят другим админом!", show_alert=True)
        return
    
    tickettakenby[ticketid] = call.from_user.id
    adminid = str(call.from_user.id)
    
    rows = []
    found = False
    with open(TICKETFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    for row in rows:
        if len(row) >= 3 and str(row[2]) == str(ticketid):
            while len(row) < 8:
                row.append("")
            row[7] = adminid
            found = True
            break
    
    if not found:
        await call.answer("❌ Тикет не найден!", show_alert=True)
        return
    
    with open(TICKETFILE, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(rows)
    
    for admin in ADMINS:
        try:
            await bot.send_message(admin, f"✅ Ticket #{ticketid} взял админ {adminid}")
        except:
            pass
    
    await state.set_state(TicketState.adminreply)
    await state.update_data(ticket=ticketid)
    await call.message.edit_reply_markup(reply_markup=ticketkeyboard(ticketid))
    await call.message.answer("✅ Тикет взят! Отправь ответ пользователю:")

@dp.message(TicketState.adminreply, F.content_type.in_({"text", "photo", "video"}))
async def adminreplymessage(message: Message, state: FSMContext):
    data = await state.get_data()
    ticketid = int(data["ticket"])
    
    userid = None
    with open(TICKETFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
        for row in rows:
            if len(row) >= 3 and str(row[2]) == str(ticketid):
                userid = int(row[0])
                break
    
    if not userid:
        await message.answer("❌ Пользователь не найден!")
        await state.clear()
        return
    
    mediatype = None
    mediaid = None
    if message.photo:
        mediatype = "photo"
        mediaid = message.photo[-1].file_id
    elif message.video:
        mediatype = "video"
        mediaid = message.video.file_id
    
    text = f"✅ Ответ от поддержки!\n\n{message.text or message.caption}\n\n📊 Ticket #{ticketid}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        ratingkeyboard(ticketid).inline_keyboard[0],
        ratingkeyboard(ticketid).inline_keyboard[1],
        [InlineKeyboardButton(text="📩 Новый тикет", callback_data="newticket"),
         InlineKeyboardButton(text="💰 Заработать голду", callback_data="earngold")]
    ])
    
    try:
        if mediatype == "photo":
            await bot.send_photo(userid, photo=mediaid, caption=text, reply_markup=kb, parse_mode="Markdown")
        elif mediatype == "video":
            await bot.send_video(userid, video=mediaid, caption=text, reply_markup=kb, parse_mode="Markdown")
        else:
            await bot.send_message(userid, text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest:
        await message.answer("❌ Не удалось отправить пользователю!")
    
    await sendwelcome(message)
    await state.clear()

@dp.callback_query(F.data.startswith("deny_"))
async def denyticketcall(call: CallbackQuery):
    ticketid = int(call.data.split("_")[1])
    if ticketid in tickettakenby and tickettakenby[ticketid] != call.from_user.id:
        await call.answer("❌ Тикет уже взят другим админом!", show_alert=True)
        return
    
    tickettakenby[ticketid] = call.from_user.id
    userid = None
    with open(TICKETFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
        for row in rows:
            if len(row) >= 3 and str(row[2]) == str(ticketid):
                userid = int(row[0])
                break
    
    if not userid:
        await call.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Новый тикет", callback_data="newticket"),
         InlineKeyboardButton(text="💰 Заработать голду", callback_data="earngold")]
    ])
    
    try:
        await bot.send_message(userid, f"❌ Ticket #{ticketid} отклонен", reply_markup=kb)
    except TelegramBadRequest:
        pass
    
    await call.message.edit_text(f"❌ Ticket #{ticketid} отклонен", parse_mode="Markdown")
    await call.answer("✅ Отклонено!")

@dp.callback_query(F.data.startswith("rate_"))
async def rateticketcall(call: CallbackQuery):
    _, stars, ticketid = call.data.split("_")
    key = f"{call.from_user.id}_{ticketid}"
    if key in ratedtickets:
        await call.answer("⭐ Уже оценил!", show_alert=True)
        return
    ratedtickets.add(key)
    
    adminid = None
    with open(TICKETFILE, 'r', newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) >= 8 and str(row[2]) == ticketid and row[7] and row[7].isdigit():
                adminid = row[7]
                break
    
    if not adminid:
        await call.answer("❌ Админ не найден!", show_alert=True)
        return
    
    with open(RATINGFILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([call.from_user.username or "", stars, adminid])
    
    for admin in ADMINS:
        await bot.send_message(admin, f"{call.from_user.username or ''} | #{ticketid} | {stars}⭐ | {adminid}")
    
    await call.message.edit_text("✅ Спасибо за оценку! ⭐")

def calculateadminrating():
    if not os.path.exists(RATINGFILE):
        return {}
    ratings = {}
    with open(RATINGFILE, 'r', newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) >= 3:
                stars = int(row[1])
                adminid = row[2]
                if adminid and adminid.isdigit():
                    if adminid not in ratings:
                        ratings[adminid] = []
                    ratings[adminid].append(stars)
    result = {}
    for adminid, starslist in ratings.items():
        avg = sum(starslist) / len(starslist)
        result[adminid] = {"rating": round(avg, 1), "count": len(starslist)}
    return result

@dp.message(Command("rating"))
async def showrating(message: Message):
    if message.from_user.id not in ADMINS:
        return
    
    ratings = calculateadminrating()
    if not ratings:
        await message.answer("📊 Нет оценок!")
        return
    
    sortedratings = sorted(ratings.items(), key=lambda x: x[1]["rating"], reverse=True)
    text = ""
    for i, (adminid, data) in enumerate(sortedratings, 1):
        text += f"{i}. {adminid} — {data['rating']}⭐ ({data['count']})\n"
    text += f"\nВсего: {len(ratings)}"
    await message.answer(text, parse_mode="Markdown")

registergoldhandlers(dp, bot)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
