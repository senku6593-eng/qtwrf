import csv
import os
import random
from datetime import datetime, timedelta

from aiogram import F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from config import ADMINS

GOLD_BALANCE_FILE = "gold_balance.csv"
GOLD_WITHDRAW_FILE = "gold_withdraw.csv"

EMOJIS = ["❄️", "💦", "☃️", "☔️", "🫧"]
EARN_COOLDOWN = 2 * 60 * 60
MIN_WITHDRAW = 50

class GoldState(StatesGroup):
    waiting_withdraw_amount = State()
    waiting_withdraw_proof = State()

def init_gold_files():
    if not os.path.exists(GOLD_BALANCE_FILE):
        with open(GOLD_BALANCE_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["user_id", "balance", "last_earn"])
    if not os.path.exists(GOLD_WITHDRAW_FILE):
        with open(GOLD_WITHDRAW_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["user_id", "username", "amount", "status", "proof_file_id"])

def get_user_row(user_id: int):
    if not os.path.exists(GOLD_BALANCE_FILE):
        return None
    with open(GOLD_BALANCE_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        if row and len(row) >= 3 and row[0] == str(user_id):
            return row
    return None

def update_balance(user_id: int, diff: int, set_last_earn: bool = False):
    if not os.path.exists(GOLD_BALANCE_FILE):
        init_gold_files()
    with open(GOLD_BALANCE_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        rows = [["user_id", "balance", "last_earn"]]
    found = False
    for i in range(1, len(rows)):
        if len(rows[i]) >= 3 and rows[i][0] == str(user_id):
            try:
                bal = int(rows[i][1])
                bal += diff
                rows[i][1] = str(max(bal, 0))
                if set_last_earn:
                    rows[i][2] = datetime.now().isoformat()
                found = True
            except (IndexError, ValueError):
                pass
            break
    if not found:
        rows.append([
            str(user_id),
            str(max(diff, 0)),
            datetime.now().isoformat() if set_last_earn else ""
        ])
    with open(GOLD_BALANCE_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

def get_balance(user_id: int) -> int:
    row = get_user_row(user_id)
    if not row or len(row) < 2:
        return 0
    try:
        return int(row[1])
    except (ValueError, IndexError):
        return 0

def can_earn(user_id: int) -> bool:
    row = get_user_row(user_id)
    if not row or len(row) < 3 or not row[2]:
        return True
    try:
        last = datetime.fromisoformat(row[2])
        return (datetime.now() - last).total_seconds() >= EARN_COOLDOWN
    except (ValueError, IndexError):
        return True

def gold_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Заработать голды", callback_data="earn_gold")],
        [InlineKeyboardButton(text="💼 Вывести голду", callback_data="withdraw_gold")],
        [InlineKeyboardButton(text="📊 Баланс", callback_data="gold_balance")]
    ])

def register_gold_handlers(dp, bot):
    init_gold_files()

    # /gold — команда показать баланс
    @dp.message(Command("gold"))
    async def cmd_gold(message: Message):
        bal = get_balance(message.from_user.id)
        mark = "✅" if bal >= MIN_WITHDRAW else "❌"
        await message.answer(
            f"Пользователь {message.from_user.id}\n"
            f"Баланс: {bal} G {mark}",
            reply_markup=gold_menu_kb()
        )

    # Кнопка «Заработать голды»
    @dp.callback_query(F.data == "earn_gold")
    async def earn_gold(call: CallbackQuery):
        if not can_earn(call.from_user.id):
            await call.answer("Можно зарабатывать голду раз в 2 часа! 🕒", show_alert=True)
            return

        # случайный выигрышный смайл (индекс 0-4)
        win_index = random.randint(0, 4)
        win_emoji = EMOJIS[win_index]
        
        # показываем смайлы в рандомном порядке, в одну строку
        emojis_shuffled = EMOJIS[:]
        random.shuffle(emojis_shuffled)

        # создаем кнопки с индексами shuffled эмодзи
        buttons = []
        for i, emoji in enumerate(emojis_shuffled):
            buttons.append(InlineKeyboardButton(text=emoji, callback_data=f"pick_{i}_{win_index}"))
        
        kb = InlineKeyboardMarkup(inline_keyboard=[buttons])  # одна строка

        await call.message.answer(
            "Привет! Я вижу ты хочешь заработать голдишки? )\n"
            "Но это не так просто.\n"
            "Угадай смайлик, от которого ты можешь выиграть голду.\n"
            "Шанс 1 к 5 🎄",
            reply_markup=kb
        )

    @dp.callback_query(F.data.startswith("pick_"))
    async def pick_emoji(call: CallbackQuery):
        _, user_choice_index, win_index = call.data.split("_")
        user_choice_index = int(user_choice_index)
        win_index = int(win_index)
        
        # строим строку результатов: ✅ только у выигрышного (win_index), ❌ у всех остальных
        result_line = "".join("✅" if i == win_index else "❌" for i in range(5))
        
        if user_choice_index == win_index:
            # ВЫИГРЫШ: 1-14 голды
            gold = random.randint(5, 15)
            update_balance(call.from_user.id, gold, set_last_earn=True)
            await call.message.edit_text(
                f"{result_line}\n\n"
                f"Ого, ты угадал! 🎉\n"
                f"Шанс 1 к 5 и ты получаешь: {gold} G\n\n"
                "Проверить баланс голды — /gold",
                reply_markup=gold_menu_kb()
            )
        else:
            # ПРОИГРЫШ: 1-5 голды (все равно дают немного)
            gold = random.randint(1, 5)
            update_balance(call.from_user.id, gold, set_last_earn=True)
            await call.message.edit_text(
                f"{result_line}\n\n"
                f"Увы, ты не угадал 😔\n"
                f"Но за участие: {gold} G\n"
                f"Попробуй через 2 часа ещё раз 🎄",
                reply_markup=gold_menu_kb()
            )

    # Кнопка «Баланс» из меню
    @dp.callback_query(F.data == "gold_balance")
    async def gold_balance(call: CallbackQuery):
        bal = get_balance(call.from_user.id)
        mark = "✅" if bal >= MIN_WITHDRAW else "❌"
        await call.message.answer(
            f"Пользователь {call.from_user.id}\n"
            f"Баланс: {bal} G {mark}",
            reply_markup=gold_menu_kb()
        )

    # Кнопка «Вывести голду»
    @dp.callback_query(F.data == "withdraw_gold")
    async def withdraw_gold(call: CallbackQuery, state: FSMContext):
        bal = get_balance(call.from_user.id)
        if bal < MIN_WITHDRAW:
            await call.answer("Недостаточно голды для вывода (минимум 50 G).", show_alert=True)
            return

        await state.set_state(GoldState.waiting_withdraw_amount)
        await call.message.answer(
            f"У вас {bal} G.\n"
            f"Минимум вывода: {MIN_WITHDRAW} G.\n"
            "Введите сумму для вывода:"
        )

    @dp.message(GoldState.waiting_withdraw_amount)
    async def process_withdraw_amount(message: Message, state: FSMContext):
        bal = get_balance(message.from_user.id)
        try:
            amount = int(message.text)
        except ValueError:
            await message.answer("Введите число.")
            return

        if amount < MIN_WITHDRAW:
            await message.answer(f"Минимум для вывода: {MIN_WITHDRAW} G.")
            return
        if amount > bal:
            await message.answer("У вас нет столько голды.")
            return

        await state.update_data(amount=amount)
        await state.set_state(GoldState.waiting_withdraw_proof)
        await message.answer(
            "Отправьте скриншот Tac 9 Tie Die за эту сумму (можно отправлять только фото)."
        )

    @dp.message(GoldState.waiting_withdraw_proof, F.photo)
    async def process_withdraw_proof(message: Message, state: FSMContext):
        data = await state.get_data()
        amount = data["amount"]
        photo_id = message.photo[-1].file_id

        # списываем голду
        update_balance(message.from_user.id, -amount, set_last_earn=False)

        # записываем заявку
        with open(GOLD_WITHDRAW_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                message.from_user.id,
                message.from_user.username,
                amount,
                "pending",
                photo_id
            ])

        await state.clear()

        await message.answer(
            "Заявка на вывод создана! 🎄\n"
            "Подождите, пока администратор проверит скриншот.",
            reply_markup=gold_menu_kb()
        )

        # шлём админам заявку на вывод
        for admin in ADMINS:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить вывод", callback_data=f"confirm_withdraw_{message.from_user.id}_{amount}")]
            ])
            await bot.send_photo(
                admin,
                photo=photo_id,
                caption=(
                    f"Заявка на вывод голды\n"
                    f"Пользователь @{message.from_user.username}\n"
                    f"Вывод: {amount} G"
                ),
                reply_markup=kb
            )

    # подтверждение вывода админом
    @dp.callback_query(F.data.startswith("confirm_withdraw_"))
    async def confirm_withdraw(call: CallbackQuery):
        if call.from_user.id not in ADMINS:
            await call.answer("Недостаточно прав.", show_alert=True)
            return

        parts = call.data.split("_")
        if len(parts) < 4:
            await call.answer("Ошибка: неверные данные.", show_alert=True)
            return

        user_id_str, amount_str = parts[2], parts[3]
        try:
            user_id = int(user_id_str)
            amount = int(amount_str)
        except ValueError:
            await call.answer("Ошибка: неверные данные.", show_alert=True)
            return

        await call.message.answer(
            "Отправьте скриншот, где вы купили скин (для отчёта). Только фото."
        )
        await call.answer("Теперь отправьте скриншот покупки.", show_alert=False)

        # уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ Вывод {amount} G подтверждён администратором! 🎄"
            )
        except Exception:
            pass
