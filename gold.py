import csv
import os
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from aiogram import F, Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties

BOTTOKEN = "8572750987:AAGHL1WKnWOfjchc-szBSwAOuTsJvNCiSlM"
ADMINS = [8414792453, 1553715060]

GOLDBALANCEFILE = "goldbalance.csv"
GOLDWITHDRAWFILE = "goldwithdraw.csv"
PROMOCODESFILE = "promocodes.csv"
PROMOUSEDFILE = "promoused.csv"

EMOJIS = ["🪙", "💰", "⭐", "🎉", "🔥"]
EARNCOOLDOWN = 2.5 * 60 * 60  # 2.5 часа (9000 секунд)
MINWITHDRAW = 50

class GoldState(StatesGroup):
    waiting_withdrawamount = State()
    waiting_withdrawproof = State()
    waiting_number = State()
    waiting_promocode = State()

def initgoldfiles():
    if not os.path.exists(GOLDBALANCEFILE):
        with open(GOLDBALANCEFILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["userid", "balance", "lastearn"])
    
    if not os.path.exists(GOLDWITHDRAWFILE):
        with open(GOLDWITHDRAWFILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["userid", "username", "amount", "status", "prooffileid"])
    
    if not os.path.exists(PROMOCODESFILE):
        with open(PROMOCODESFILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["code", "maxuses", "currentuses", "goldamount", "createdby", "createdat"])
    
    if not os.path.exists(PROMOUSEDFILE):
        with open(PROMOUSEDFILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["userid", "promocode", "usedat"])

def getuserrow(userid: int):
    if not os.path.exists(GOLDBALANCEFILE):
        return None
    with open(GOLDBALANCEFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
        for row in rows[1:]:
            if row and len(row) >= 3 and row[0] == str(userid):
                return row
    return None

def updatebalance(userid: int, diff: int, setlastearn: bool = False):
    if not os.path.exists(GOLDBALANCEFILE):
        initgoldfiles()
    
    with open(GOLDBALANCEFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    
    if not rows:
        rows = [["userid", "balance", "lastearn"]]
    
    found = False
    for i in range(1, len(rows)):
        if len(rows[i]) >= 3 and rows[i][0] == str(userid):
            try:
                bal = int(rows[i][1])
                bal += diff
                rows[i][1] = str(max(bal, 0))
                if setlastearn:
                    rows[i][2] = datetime.now().isoformat()
                found = True
            except (IndexError, ValueError):
                pass
            break
    
    if not found:
        rows.append([str(userid), str(max(diff, 0)), "0" if setlastearn else ""])
    
    with open(GOLDBALANCEFILE, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(rows)

def getbalance(userid: int) -> int:
    row = getuserrow(userid)
    if not row or len(row) < 2:
        return 0
    try:
        return int(row[1])
    except (ValueError, IndexError):
        return 0

def canearn(userid: int) -> bool:
    row = getuserrow(userid)
    if not row or len(row) < 3 or not row[2]:
        return True
    try:
        last = datetime.fromisoformat(row[2])
        return (datetime.now() - last).total_seconds() > EARNCOOLDOWN
    except (ValueError, IndexError):
        return True

def hasuserusedpromo(userid: int, promocode: str) -> bool:
    if not os.path.exists(PROMOUSEDFILE):
        return False
    with open(PROMOUSEDFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
        for row in rows[1:]:
            if len(row) >= 2 and row[0] == str(userid) and row[1].lower() == promocode.lower():
                return True
    return False

def markpromoused(userid: int, promocode: str):
    with open(PROMOUSEDFILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([userid, promocode.upper(), datetime.now().isoformat()])

def createpromocode(code: str, maxuses: int, goldamount: int, adminid: int) -> bool:
    with open(PROMOCODESFILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([code.upper(), maxuses, 0, goldamount, adminid, datetime.now().isoformat()])
    return True

def getpromocodes() -> List[Dict]:
    if not os.path.exists(PROMOCODESFILE):
        return []
    with open(PROMOCODESFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
        promos = []
        for row in rows[1:]:
            if len(row) >= 6 and int(row[2]) < int(row[1]):
                promos.append({
                    "code": row[0],
                    "maxuses": int(row[1]),
                    "currentuses": int(row[2]),
                    "goldamount": int(row[3])
                })
        return promos

def deletepromocode(code: str) -> bool:
    if not os.path.exists(PROMOCODESFILE):
        return False
    with open(PROMOCODESFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    
    newrows = [rows[0]]
    deleted = False
    for row in rows[1:]:
        if row and row[0].lower() == code.lower():
            deleted = True
            continue
        newrows.append(row)
    
    if deleted:
        with open(PROMOCODESFILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(newrows)
        return True
    return False

def usepromocode(code: str, userid: int) -> Optional[int]:
    if not os.path.exists(PROMOCODESFILE):
        return None
    
    if hasuserusedpromo(userid, code):
        return None
    
    with open(PROMOCODESFILE, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    
    for i, row in enumerate(rows[1:], 1):
        if len(row) >= 4 and row[0].lower() == code.lower():
            maxuses = int(row[1])
            currentuses = int(row[2])
            goldamount = int(row[3])
            
            if currentuses >= maxuses:
                return None
            
            rows[i][2] = str(currentuses + 1)
            with open(PROMOCODESFILE, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerows(rows)
            
            markpromoused(userid, code)
            return goldamount
    return None

def goldmenukb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎄 Заработать", callback_data="earngold"),
            InlineKeyboardButton(text="🎁 Промокод", callback_data="usepromo")
        ],
        [
            InlineKeyboardButton(text="💰 Вывод", callback_data="withdrawgold"),
            InlineKeyboardButton(text="❄️ Баланс", callback_data="goldbalance")
        ]
    ])

def promolistkb(promos: List[Dict]):
    keyboard = []
    for promo in promos:
        remaining = promo["maxuses"] - promo["currentuses"]
        text = f"🎁 {promo['code']} ({remaining}/{promo['maxuses']})"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"adminpromo_{promo['code']}")])
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="closepromo")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def registergoldhandlers(dp: Dispatcher, bot: Bot):
    initgoldfiles()
    
    @dp.message(Command("gold"))
    async def cmdgold(message: Message):
        bal = getbalance(message.from_user.id)
        mark = "💎" if bal >= MINWITHDRAW else ""
        await message.answer(
            f"🎄 <b>ID: `{message.from_user.id}`</b>\n\n"
            f"💰 <b>Баланс: {bal} G</b> {mark}\n\n"
            f"🎅 <b>НОВОГОДНЕЕ МЕНЮ:</b> ❄️",
            reply_markup=goldmenukb(),
            parse_mode="HTML"
        )
    
    @dp.callback_query(F.data == "earngold")
    async def earngoldcall(call: CallbackQuery, state: FSMContext):
        if not canearn(call.from_user.id):
            await call.answer("⏱️ 2.5 часа между заработками! ❄️", show_alert=True)
            return
        
        winindex = random.randint(0, 4)
        await state.update_data(winindex=winindex)
        await state.set_state(GoldState.waiting_number)
        await call.message.edit_text(
            f"🎲 <b>❄️ НОВОГОДНЯЯ ЛОТЕРЕЯ ❄️</b>\n\n"
            f"🎄 Угадай правильный слот!\n\n"
            f"🆔 <code>{call.from_user.id}</code>\n\n"
            f"💰 <b>1, 2, 3, 4 или 5</b> 🎁",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancelearn")]
            ]),
            parse_mode="HTML"
        )
    
    @dp.message(GoldState.waiting_number)
    async def processusernumber(message: Message, state: FSMContext):
        data = await state.get_data()
        winindex = data.get('winindex', 0)
        
        if not re.match(r'^\s*[1-5]\s*$', message.text.strip()):
            await message.answer(
                "❌ <b>Введи 1-5!</b>\n\n<code>4</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 ❄️ Попробовать снова ❄️", callback_data="earngold")]
                ])
            )
            return
        
        userchoice = int(message.text.strip()) - 1
        resultline = "".join("✅" if i == winindex else "❌" for i in range(5))
        
        if userchoice == winindex:
            gold = random.randint(5, 15)
            updatebalance(message.from_user.id, gold, setlastearn=True)
            await message.answer(
                f"🎉 <b>🎅 САНТА ПРИНЕС ПОДАРОК! 🎁</b>\n\n"
                f"{resultline}\n\n"
                f"❄️ <b>+{gold} G</b> ✨\n\n"
                f"<code>/gold</code> 🎄",
                reply_markup=goldmenukb(),
                parse_mode="HTML"
            )
        else:
            gold = random.randint(1, 5)
            updatebalance(message.from_user.id, gold, setlastearn=True)
            await message.answer(
                f"😔 <b>Не угадал...</b> 🎄\n\n"
                f"{resultline}\n\n"
                f"💰 <b>+{gold} G</b> 🎁\n\n"
                f"⏳ <b>2.5 часа до следующей попытки!</b> ❄️",
                reply_markup=goldmenukb(),
                parse_mode="HTML"
            )
        await state.clear()
    
    @dp.callback_query(F.data == "cancelearn")
    async def cancelearncall(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text(
            "❌ <b>Отменено!</b> 🎄",
            reply_markup=goldmenukb(),
            parse_mode="HTML"
        )
    
    @dp.callback_query(F.data == "goldbalance")
    async def goldbalancecall(call: CallbackQuery):
        bal = getbalance(call.from_user.id)
        mark = "💎" if bal >= MINWITHDRAW else ""
        await call.message.answer(
            f"🆔 ID: <code>{call.from_user.id}</code>\n\n"
            f"💰 Баланс: <b>{bal}</b> G {mark}",
            reply_markup=goldmenukb(),
            parse_mode="HTML"
        )
    
    @dp.callback_query(F.data == "withdrawgold")
    async def withdrawgoldcall(call: CallbackQuery, state: FSMContext):
        bal = getbalance(call.from_user.id)
        if bal < MINWITHDRAW:
            await call.answer(f"💰 Минимум {MINWITHDRAW} G!", show_alert=True)
            return
        
        await state.set_state(GoldState.waiting_withdrawamount)
        await call.message.answer(
            f"🎄 <b>Баланс: {bal} G</b>\n\n"
            f"💎 <b>Минимум {MINWITHDRAW} G</b>\n\n"
            f"🎁 <b>Сумма вывода:</b> ❄️",
            parse_mode="HTML"
        )
    
    @dp.message(GoldState.waiting_withdrawamount)
    async def processwithdrawamount(message: Message, state: FSMContext):
        bal = getbalance(message.from_user.id)
        try:
            amount = int(message.text)
        except ValueError:
            await message.answer("❌ Введи число!")
            return
        
        if amount < MINWITHDRAW:
            await message.answer(f"💰 Минимум {MINWITHDRAW} G!")
            return
        if amount > bal:
            await message.answer("❌ Недостаточно!")
            return
        
        await state.update_data(amount=amount)
        await state.set_state(GoldState.waiting_withdrawproof)
        await message.answer(
            f"📸 <b>❄️ Скриншот Tie Dye ❄️</b>\n\n"
            f"💎 <b>{amount} G</b>! 🎁\n\n"
            f"✅ <b>Только после подтверждения!</b> 🎅",
            parse_mode="HTML"
        )
    
    @dp.message(GoldState.waiting_withdrawproof, F.photo)
    async def processwithdrawproof(message: Message, state: FSMContext):
        data = await state.get_data()
        amount = data["amount"]
        photoid = message.photo[-1].file_id
        
        updatebalance(message.from_user.id, -amount, setlastearn=False)
        with open(GOLDWITHDRAWFILE, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                message.from_user.id,
                message.from_user.username or "nousername",
                amount, "pending", photoid
            ])
        
        await state.clear()
        await message.answer(
            "✅ <b>Заявка создана!</b>\n✅ Ожидайте выплату! 🎄",
            reply_markup=goldmenukb(),
            parse_mode="HTML"
        )
        
        for admin in ADMINS:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirmwithdraw_{message.from_user.id}_{amount}")]
            ])
            try:
                await message.bot.send_photo(
                    admin, photo=photoid,
                    caption=f"💰 <b>Заявка на вывод</b>\n\n"
                            f"👤 {message.from_user.username or 'nousername'}\n"
                            f"💎 {amount} G",
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except:
                pass
    
    @dp.message(Command("promo"))
    async def cmdpromo(message: Message, state: FSMContext):
        await state.set_state(GoldState.waiting_promocode)
        await message.answer(
            f"🎁 <b>🎄 НОВОГОДНИЙ ПРОМОКОД 🎅</b>\n\n"
            f"💎 <b>Введи код:</b> ❄️",
            parse_mode="HTML"
        )
    
    @dp.message(GoldState.waiting_promocode)
    async def processpromo(message: Message, state: FSMContext):
        code = message.text.strip().upper()
        gold = usepromocode(code, message.from_user.id)
        
        if gold:
            updatebalance(message.from_user.id, gold, setlastearn=False)
            bal = getbalance(message.from_user.id)
            await message.answer(
                f"🎉 <b>🎁 АКТИВИРОВАН! ❄️</b>\n\n"
                f"💎 <b>+{gold}</b> G\n"
                f"💰 <b>Баланс: {bal}</b> G\n\n"
                f"🎄 <code>{code}</code>\n"
                f"✨ <b>С Новым годом! 🎅</b>",
                reply_markup=goldmenukb(),
                parse_mode="HTML"
            )
        else:
            if hasuserusedpromo(message.from_user.id, code):
                await message.answer(
                    f"🎁 Код: <code>{code}</code>\n\n"
                    f"❌ <b>Уже использовал!</b>\n"
                    f"❌ Один раз на аккаунт!",
                    reply_markup=goldmenukb(),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    f"🎁 Код: <code>{code}</code>\n\n"
                    f"❌ <b>Неверный/истек!</b>",
                    reply_markup=goldmenukb(),
                    parse_mode="HTML"
                )
        await state.clear()
    
    @dp.callback_query(F.data == "usepromo")
    async def btnusepromocall(call: CallbackQuery, state: FSMContext):
        await call.message.answer(
            "🎁 <code>/promo КОД</code>",
            reply_markup=goldmenukb(),
            parse_mode="HTML"
        )
    
    @dp.message(Command("cpromo"))
    async def cmdcreatepromo(message: Message):
        if message.from_user.id not in ADMINS:
            await message.answer("❌ Нет доступа!")
            return
        
        match = re.match(r'/cpromo\s+(\d+)\s+(\d+)\s+(.+)', message.text)
        if not match:
            await message.answer(
                "❌\n\n<code>/cpromo 3 30 WIAZY</code>\n\n"
                "👉 активаций | голды | код",
                parse_mode="HTML"
            )
            return
        
        maxuses, goldamount, code = int(match.group(1)), int(match.group(2)), match.group(3).strip().upper()
        if createpromocode(code, maxuses, goldamount, message.from_user.id):
            await message.answer(
                f"✅ <b>Создан!</b>\n\n"
                f"<code>{code}</code>\n"
                f"🔢 Активаций: <b>{maxuses}</b>\n"
                f"💎 Голды: <b>{goldamount}</b> G\n\n"
                f"✨ Готов к использованию! ✨",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка!")
    
    @dp.message(Command("dpromo"))
    async def cmddeletepromo(message: Message):
        if message.from_user.id not in ADMINS:
            await message.answer("❌ Нет доступа!")
            return
        
        promos = getpromocodes()
        if not promos:
            await message.answer("❌ Промокодов нет!")
            return
        
        await message.answer(
            f"📱 <b>{len(promos)} промокод(а/ов)</b>",
            reply_markup=promolistkb(promos),
            parse_mode="HTML"
        )
    
    @dp.callback_query(F.data.startswith("adminpromo_"))
    async def adminpromostatscall(call: CallbackQuery):
        if call.from_user.id not in ADMINS:
            await call.answer("❌ Нет доступа!", show_alert=True)
            return
        
        try:
            code = call.data.replace("adminpromo_", "")
            if not code:
                await call.answer("❌ Неверный промокод!", show_alert=True)
                return
        except:
            await call.answer("❌ Ошибка данных!", show_alert=True)
            return
        
        promos = getpromocodes()
        promo_found = False
        for promo in promos:
            if promo["code"] == code:
                remaining = promo["maxuses"] - promo["currentuses"]
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"deletepromo_{code}")],
                    [InlineKeyboardButton(text="❌ Закрыть", callback_data="closepromo")]
                ])
                await call.message.edit_text(
                    f"🎁 <b>{code}</b>\n\n"
                    f"Всего: {promo['maxuses']}\n"
                    f"Использовано: {promo['currentuses']}\n"
                    f"Осталось: <b>{remaining}</b>\n\n"
                    f"💎 Награда: {promo['goldamount']} G",
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                promo_found = True
                break
        
        if not promo_found:
            await call.answer("❌ Промокод не найден!", show_alert=True)
    
    @dp.callback_query(F.data.startswith("deletepromo_"))
    async def deletepromocall(call: CallbackQuery):
        if call.from_user.id not in ADMINS:
            await call.answer("❌ Нет доступа!", show_alert=True)
            return
        
        try:
            code = call.data.replace("deletepromo_", "")
            if not code:
                await call.answer("❌ Неверный промокод!", show_alert=True)
                return
        except:
            await call.answer("❌ Ошибка данных!", show_alert=True)
            return
        
        if deletepromocode(code):
            await call.message.edit_text(
                f"🎁 <b>{code}</b>\n\n✅ <b>Промокод удален!</b> 🎄",
                reply_markup=goldmenukb(),
                parse_mode="HTML"
            )
        else:
            await call.answer("❌ Ошибка удаления!", show_alert=True)
    
    @dp.callback_query(F.data == "closepromo")
    async def closepromocall(call: CallbackQuery):
        try:
            await call.message.delete()
        except:
            pass
        await call.message.answer("🔙 Главное меню", reply_markup=goldmenukb())
    
    @dp.callback_query(F.data.startswith("confirmwithdraw_"))
    async def confirmwithdrawcall(call: CallbackQuery):
        if call.from_user.id not in ADMINS:
            await call.answer("❌ Нет доступа!", show_alert=True)
            return
        
        parts = call.data.split("_")
        if len(parts) < 4:
            await call.answer("❌ Неверные данные!", show_alert=True)
            return
        
        try:
            userid = int(parts[2])
            amount = int(parts[3])
            await call.message.answer("✅ Выплата подтверждена! 🎄")
            await call.bot.send_message(userid, f"💰 <b>{amount} G</b> выплачено! 🎁", parse_mode="HTML")
        except:
            await call.answer("❌ Ошибка обработки!", show_alert=True)

if __name__ == "__main__":
    bot = Bot(token=BOTTOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    registergoldhandlers(dp, bot)
    print("🚀 Gold бот запущен! 🎄❄️")
    import asyncio
    asyncio.run(dp.start_polling(bot))
