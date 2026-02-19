from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from states import AddClient, EditClient, PostponePayment, DeleteClient, ViewHistory, SearchClient
import database as db
import keyboards as kb
import utils
from datetime import datetime, date
from logger import logger
from config import Config
import csv
import io
import os

router = Router()


# ============================================================================
# MIDDLEWARE & DECORATORS
# ============================================================================

def require_auth(handler):
    """Decorator to check user access"""
    async def wrapper(message: types.Message, *args, **kwargs):
        if not await utils.check_user_access(message):
            return
        return await handler(message, *args, **kwargs)
    return wrapper


# ============================================================================
# BASIC COMMANDS
# ============================================================================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start command handler"""
    if not await utils.check_user_access(message):
        return
    
    user_name = message.from_user.first_name or "пользователь"
    await message.answer(
        f"👋 <b>Добро пожаловать, {user_name}!</b>\n\n"
        "Я помогу вам отслеживать платежи клиентов.\n\n"
        "📋 <b>Основные функции:</b>\n"
        "• Добавление и редактирование клиентов\n"
        "• Автоматические напоминания о платежах\n"
        "• История платежей и статистика\n"
        "• Экспорт данных\n\n"
        "Используйте меню ниже для управления клиентами.",
        reply_markup=kb.get_main_keyboard(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} (@{message.from_user.username}) started the bot")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Help command"""
    if not await utils.check_user_access(message):
        return
    
    help_text = (
        "📖 <b>Справка по использованию бота</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - Запустить бота\n"
        "/help - Показать эту справку\n"
        "/cancel - Отменить текущее действие\n\n"
        "<b>Кнопки меню:</b>\n"
        "➕ Добавить клиента - Добавить нового клиента\n"
        "📋 Список клиентов - Показать всех клиентов\n"
        "💰 Отметить оплату - Отметить платеж как оплаченный\n"
        "✏️ Редактировать - Изменить данные клиента\n"
        "📊 Статистика - Показать статистику\n"
        "📜 История - Показать историю платежей\n"
        "💾 Бэкап - Создать резервную копию данных\n"
        "❌ Удалить клиента - Удалить клиента из базы\n\n"
        "<b>Автоматические напоминания:</b>\n"
        f"Бот проверяет платежи каждый день в {Config.CHECK_TIME_HOUR:02d}:{Config.CHECK_TIME_MINUTE:02d}\n"
        "и отправляет напоминания о просроченных и предстоящих платежах."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("отмена"))
@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Cancel current operation"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных операций для отмены.", reply_markup=kb.get_main_keyboard())
        return
    
    await state.clear()
    await message.answer("✅ Действие отменено.", reply_markup=kb.get_main_keyboard())
    logger.info(f"User {message.from_user.id} cancelled operation: {current_state}")


# ============================================================================
# ADD CLIENT FLOW
# ============================================================================

@router.message(F.text == "➕ Добавить клиента")
async def start_add_client(message: types.Message, state: FSMContext):
    """Start adding a new client"""
    if not await utils.check_user_access(message):
        return
    
    await state.set_state(AddClient.waiting_for_name)
    await message.answer(
        "📝 <b>Добавление нового клиента</b>\n\n"
        "Введите имя клиента:",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddClient.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    """Process client name"""
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Введите хотя бы 2 символа.")
        return
    
    await state.update_data(name=name)
    await state.set_state(AddClient.waiting_for_amount)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "💰 Введите сумму платежа (например, 5000 или 5000.50):",
        parse_mode="HTML"
    )


@router.message(AddClient.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    """Process payment amount"""
    valid, amount, error_msg = utils.validate_amount(message.text)
    
    if not valid:
        await message.answer(f"❌ {error_msg}\n\nПопробуйте еще раз:")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(AddClient.waiting_for_currency)
    await message.answer(
        f"✅ Сумма: <b>{amount}</b>\n\n"
        "💱 Выберите валюту:",
        reply_markup=kb.get_currency_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(AddClient.waiting_for_currency, F.data.startswith("curr_"))
async def process_currency(callback: types.CallbackQuery, state: FSMContext):
    """Process currency selection"""
    currency = callback.data.split("_")[1]
    await state.update_data(currency=currency)
    
    data = await state.get_data()
    await state.set_state(AddClient.waiting_for_start_date)
    
    await callback.message.edit_text(
        f"✅ Валюта: <b>{currency}</b>\n\n"
        "📅 Введите дату следующего платежа в формате ДД.ММ.ГГГГ\n"
        "(например, 15.02.2026):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddClient.waiting_for_start_date)
async def process_date(message: types.Message, state: FSMContext):
    """Process payment date"""
    parsed_date = utils.parse_date(message.text)
    
    if not parsed_date:
        await message.answer(
            "❌ Неверный формат даты.\n\n"
            "Используйте формат ДД.ММ.ГГГГ (например, 15.02.2026):"
        )
        return
    
    await state.update_data(start_date=parsed_date.isoformat())
    await state.set_state(AddClient.waiting_for_interval_type)
    await message.answer(
        f"✅ Дата платежа: <b>{utils.format_date(parsed_date)}</b>\n\n"
        "🔄 Выберите интервал платежей:",
        reply_markup=kb.get_interval_type_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(AddClient.waiting_for_interval_type, F.data.startswith("interval_"))
async def process_interval_type(callback: types.CallbackQuery, state: FSMContext):
    """Process interval type selection"""
    interval = callback.data.split("_")[1]
    await state.update_data(interval_type=interval)
    await state.set_state(AddClient.waiting_for_interval_value)
    
    interval_prompts = {
        'weekly': "Каждые сколько недель? (например, 1, 2, 3...)",
        'monthly': "Каждые сколько месяцев? (введите 1 для ежемесячного)",
        'yearly': "Каждые сколько лет? (введите 1 для ежегодного)"
    }
    
    await callback.message.edit_text(
        f"✅ Тип интервала: <b>{interval}</b>\n\n"
        f"{interval_prompts.get(interval, 'Введите значение интервала:')}",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddClient.waiting_for_interval_value)
async def process_interval_value(message: types.Message, state: FSMContext):
    """Process interval value"""
    valid, interval_value, error_msg = utils.validate_interval_value(message.text)
    
    if not valid:
        await message.answer(f"❌ {error_msg}\n\nПопробуйте еще раз:")
        return
    
    await state.update_data(interval_value=interval_value)
    data = await state.get_data()
    
    await state.set_state(AddClient.waiting_for_category)
    await message.answer(
        f"✅ Интервал: <b>{utils.get_interval_description(data['interval_type'], interval_value)}</b>\n\n"
        "🏷️ Выберите категорию клиента:",
        reply_markup=kb.get_category_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(AddClient.waiting_for_category, F.data.startswith("cat_"))
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    """Process category selection"""
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await state.set_state(AddClient.waiting_for_notes)
    
    await callback.message.edit_text(
        f"✅ Категория: <b>{category}</b>\n\n"
        "📝 Введите заметки о клиенте (или отправьте '-' чтобы пропустить):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddClient.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    """Process notes and save client"""
    notes = message.text.strip() if message.text.strip() != '-' else ''
    data = await state.get_data()
    
    # Save to database
    client_id = await db.add_client(
        user_id=message.from_user.id,
        name=data['name'],
        amount=data['amount'],
        currency=data['currency'],
        start_date=data['start_date'],
        interval_type=data['interval_type'],
        interval_value=data['interval_value'],
        category=data['category'],
        notes=notes
    )
    
    if client_id:
        summary = (
            "✅ <b>Клиент успешно добавлен!</b>\n\n"
            f"👤 Имя: {data['name']}\n"
            f"💰 Сумма: {utils.format_currency(data['amount'], data['currency'])}\n"
            f"📅 Дата платежа: {utils.format_date(datetime.fromisoformat(data['start_date']).date())}\n"
            f"🔄 Интервал: {utils.get_interval_description(data['interval_type'], data['interval_value'])}\n"
            f"🏷️ Категория: {data['category']}\n"
        )
        if notes:
            summary += f"📝 Заметки: {notes}\n"
        
        await message.answer(summary, reply_markup=kb.get_main_keyboard(), parse_mode="HTML")
        logger.info(f"User {message.from_user.id} added client: {data['name']} (ID: {client_id})")
    else:
        await message.answer(
            "❌ Ошибка при добавлении клиента. Попробуйте еще раз.",
            reply_markup=kb.get_main_keyboard()
        )
    
    await state.clear()


# ============================================================================
# LIST CLIENTS
# ============================================================================

@router.message(F.text == "📋 Список клиентов")
async def list_clients(message: types.Message):
    """Show list of all clients"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer(
            "📋 <b>Список клиентов пуст</b>\n\n"
            "Используйте кнопку '➕ Добавить клиента' для добавления первого клиента.",
            parse_mode="HTML"
        )
        return
    
    # Group clients by status
    overdue = []
    upcoming = []
    future = []
    
    today = date.today()
    
    for client in clients:
        next_payment = datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()
        days_until = utils.get_days_until(next_payment)
        
        if days_until < 0:
            overdue.append(client)
        elif days_until <= 3:
            upcoming.append(client)
        else:
            future.append(client)
    
    response = "📋 <b>Ваши клиенты</b>\n\n"
    
    if overdue:
        response += "🔴 <b>Просроченные платежи:</b>\n"
        for client in overdue:
            response += utils.format_client_info(client, show_details=False) + "\n"
    
    if upcoming:
        response += "🟡 <b>Скоро (в течение 3 дней):</b>\n"
        for client in upcoming:
            response += utils.format_client_info(client, show_details=False) + "\n"
    
    if future:
        response += "🟢 <b>Будущие платежи:</b>\n"
        for client in future[:10]:  # Show only first 10
            response += utils.format_client_info(client, show_details=False) + "\n"
        
        if len(future) > 10:
            response += f"\n... и еще {len(future) - 10} клиентов\n"
    
    response += f"\n<b>Всего клиентов:</b> {len(clients)}"
    
    await utils.send_long_message(message, response, parse_mode="HTML")
    logger.info(f"User {message.from_user.id} viewed client list ({len(clients)} clients)")


# ============================================================================
# MARK PAYMENT
# ============================================================================

@router.message(F.text == "💰 Отметить оплату")
async def start_mark_payment(message: types.Message):
    """Start payment marking process"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer("Нет клиентов для отметки оплаты.")
        return
    
    await message.answer(
        "💰 <b>Отметить оплату</b>\n\n"
        "Выберите клиента:",
        reply_markup=kb.get_client_list_keyboard(clients, "pay"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pay_"))
async def process_payment_selection(callback: types.CallbackQuery):
    """Process client selection for payment"""
    client_id = int(callback.data.split("_")[1])
    client = await db.get_client_by_id(client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"💰 <b>Отметить оплату</b>\n\n"
        f"{utils.format_client_info(client)}\n"
        "Выберите действие:",
        reply_markup=kb.get_payment_status_keyboard(client_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("status_"))
async def process_payment_status(callback: types.CallbackQuery):
    """Process payment status selection"""
    parts = callback.data.split("_")
    status = parts[1]
    
    # Handle postpone with days
    if status == "postpone":
        days = int(parts[2]) if len(parts) > 2 else 7
        client_id = int(parts[3]) if len(parts) > 3 else int(parts[2])
    else:
        client_id = int(parts[2])
        days = 7
    
    success = await db.mark_payment_status(client_id, status, days)
    
    if success:
        messages = {
            'paid': '✅ Платёж отмечен как оплаченный!\nСледующая дата платежа обновлена.',
            'unpaid': '❌ Платёж отмечен как неоплаченный.',
            'postpone': f'⏰ Платёж отложен на {days} дн.'
        }
        await callback.message.edit_text(
            messages.get(status, 'Статус обновлён.'),
            parse_mode="HTML"
        )
        logger.info(f"Payment status updated for client {client_id}: {status}")
    else:
        await callback.message.edit_text("❌ Ошибка при обновлении статуса.")
    
    await callback.answer()


# ============================================================================
# EDIT CLIENT
# ============================================================================

@router.message(F.text == "✏️ Редактировать")
async def start_edit_client(message: types.Message, state: FSMContext):
    """Start client editing process"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer("Нет клиентов для редактирования.")
        return
    
    await state.set_state(EditClient.selecting_client)
    await message.answer(
        "✏️ <b>Редактирование клиента</b>\n\n"
        "Выберите клиента:",
        reply_markup=kb.get_client_list_keyboard(clients, "edit"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^edit_\d+$"))
async def process_edit_selection(callback: types.CallbackQuery, state: FSMContext):
    """Process client selection for editing"""
    client_id = int(callback.data.split("_")[1])
    client = await db.get_client_by_id(client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    await state.update_data(client_id=client_id)
    await state.set_state(EditClient.selecting_field)
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование клиента</b>\n\n"
        f"{utils.format_client_info(client)}\n"
        "Что хотите изменить?",
        reply_markup=kb.get_edit_options_keyboard(client_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(EditClient.selecting_field, F.data.startswith("edit_"))
async def process_field_selection(callback: types.CallbackQuery, state: FSMContext):
    """Process field selection for editing"""
    parts = callback.data.split("_")
    field = parts[1]
    
    if field == "cancel":
        await state.clear()
        await callback.message.edit_text("✅ Редактирование отменено.")
        await callback.answer()
        return
    
    client_id = int(parts[2])
    await state.update_data(field=field, client_id=client_id)
    
    prompts = {
        'name': ('waiting_for_name', "Введите новое имя клиента:"),
        'amount': ('waiting_for_amount', "Введите новую сумму платежа:"),
        'currency': ('waiting_for_currency', "Выберите новую валюту:"),
        'date': ('waiting_for_date', "Введите новую дату платежа (ДД.ММ.ГГГГ):"),
        'interval': ('waiting_for_interval_type', "Выберите новый интервал:"),
        'category': ('waiting_for_category', "Выберите новую категорию:"),
        'notes': ('waiting_for_notes', "Введите новые заметки:")
    }
    
    if field in prompts:
        state_name, prompt = prompts[field]
        await state.set_state(getattr(EditClient, state_name))
        
        if field == 'currency':
            await callback.message.edit_text(prompt, reply_markup=kb.get_currency_keyboard())
        elif field == 'interval':
            await callback.message.edit_text(prompt, reply_markup=kb.get_interval_type_keyboard())
        elif field == 'category':
            await callback.message.edit_text(prompt, reply_markup=kb.get_category_keyboard())
        else:
            await callback.message.edit_text(prompt)
    
    await callback.answer()


@router.message(EditClient.waiting_for_name)
async def edit_name(message: types.Message, state: FSMContext):
    """Edit client name"""
    data = await state.get_data()
    success = await db.update_client(data['client_id'], name=message.text.strip())
    
    if success:
        await message.answer("✅ Имя клиента обновлено!", reply_markup=kb.get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=kb.get_main_keyboard())
    
    await state.clear()


@router.message(EditClient.waiting_for_amount)
async def edit_amount(message: types.Message, state: FSMContext):
    """Edit payment amount"""
    valid, amount, error_msg = utils.validate_amount(message.text)
    
    if not valid:
        await message.answer(f"❌ {error_msg}\n\nПопробуйте еще раз:")
        return
    
    data = await state.get_data()
    success = await db.update_client(data['client_id'], amount=amount)
    
    if success:
        await message.answer("✅ Сумма платежа обновлена!", reply_markup=kb.get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=kb.get_main_keyboard())
    
    await state.clear()


@router.callback_query(EditClient.waiting_for_currency, F.data.startswith("curr_"))
async def edit_currency(callback: types.CallbackQuery, state: FSMContext):
    """Edit currency"""
    currency = callback.data.split("_")[1]
    data = await state.get_data()
    success = await db.update_client(data['client_id'], currency=currency)
    
    if success:
        await callback.message.edit_text("✅ Валюта обновлена!")
    else:
        await callback.message.edit_text("❌ Ошибка при обновлении")
    
    await state.clear()
    await callback.answer()


@router.message(EditClient.waiting_for_date)
async def edit_date(message: types.Message, state: FSMContext):
    """Edit payment date"""
    parsed_date = utils.parse_date(message.text)
    
    if not parsed_date:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
        return
    
    data = await state.get_data()
    success = await db.update_client(data['client_id'], next_payment_date=parsed_date.isoformat())
    
    if success:
        await message.answer("✅ Дата платежа обновлена!", reply_markup=kb.get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=kb.get_main_keyboard())
    
    await state.clear()


@router.callback_query(EditClient.waiting_for_interval_type, F.data.startswith("interval_"))
async def edit_interval_type(callback: types.CallbackQuery, state: FSMContext):
    """Edit interval type"""
    interval_type = callback.data.split("_")[1]
    await state.update_data(interval_type=interval_type)
    await state.set_state(EditClient.waiting_for_interval_value)
    
    await callback.message.edit_text(
        f"Выбран интервал: {interval_type}\n\n"
        "Введите значение интервала (например, 1, 2, 3...):"
    )
    await callback.answer()


@router.message(EditClient.waiting_for_interval_value)
async def edit_interval_value(message: types.Message, state: FSMContext):
    """Edit interval value"""
    valid, interval_value, error_msg = utils.validate_interval_value(message.text)
    
    if not valid:
        await message.answer(f"❌ {error_msg}\n\nПопробуйте еще раз:")
        return
    
    data = await state.get_data()
    success = await db.update_client(
        data['client_id'],
        interval_type=data['interval_type'],
        interval_value=interval_value
    )
    
    if success:
        await message.answer("✅ Интервал платежей обновлен!", reply_markup=kb.get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=kb.get_main_keyboard())
    
    await state.clear()


@router.callback_query(EditClient.waiting_for_category, F.data.startswith("cat_"))
async def edit_category(callback: types.CallbackQuery, state: FSMContext):
    """Edit category"""
    category = callback.data.split("_")[1]
    data = await state.get_data()
    success = await db.update_client(data['client_id'], category=category)
    
    if success:
        await callback.message.edit_text("✅ Категория обновлена!")
    else:
        await callback.message.edit_text("❌ Ошибка при обновлении")
    
    await state.clear()
    await callback.answer()


@router.message(EditClient.waiting_for_notes)
async def edit_notes(message: types.Message, state: FSMContext):
    """Edit notes"""
    data = await state.get_data()
    notes = message.text.strip() if message.text.strip() != '-' else ''
    success = await db.update_client(data['client_id'], notes=notes)
    
    if success:
        await message.answer("✅ Заметки обновлены!", reply_markup=kb.get_main_keyboard())
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=kb.get_main_keyboard())
    
    await state.clear()


# ============================================================================
# DELETE CLIENT
# ============================================================================

@router.message(F.text == "❌ Удалить клиента")
async def start_delete_client(message: types.Message, state: FSMContext):
    """Start client deletion process"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer("Нет клиентов для удаления.")
        return
    
    await state.set_state(DeleteClient.selecting_client)
    await message.answer(
        "🗑️ <b>Удаление клиента</b>\n\n"
        "Выберите клиента для удаления:",
        reply_markup=kb.get_client_list_keyboard(clients, "delete"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("delete_"))
async def process_delete_selection(callback: types.CallbackQuery, state: FSMContext):
    """Process client selection for deletion"""
    client_id = int(callback.data.split("_")[1])
    client = await db.get_client_by_id(client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    await state.update_data(client_id=client_id)
    await state.set_state(DeleteClient.confirming)
    
    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы уверены, что хотите удалить клиента?\n\n"
        f"{utils.format_client_info(client)}\n"
        f"<b>Это действие нельзя отменить!</b>",
        reply_markup=kb.get_confirmation_keyboard("delete", client_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(DeleteClient.confirming, F.data.startswith("confirm_delete_"))
async def confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    """Confirm and delete client"""
    client_id = int(callback.data.split("_")[2])
    success = await db.delete_client(client_id)
    
    if success:
        await callback.message.edit_text("✅ Клиент успешно удалён.")
        logger.info(f"User {callback.from_user.id} deleted client {client_id}")
    else:
        await callback.message.edit_text("❌ Ошибка при удалении клиента.")
    
    await state.clear()
    await callback.answer()


@router.callback_query(DeleteClient.confirming, F.data.startswith("cancel_delete_"))
async def cancel_delete(callback: types.CallbackQuery, state: FSMContext):
    """Cancel deletion"""
    await callback.message.edit_text("✅ Удаление отменено.")
    await state.clear()
    await callback.answer()


# ============================================================================
# STATISTICS
# ============================================================================

@router.message(F.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    """Show user statistics"""
    if not await utils.check_user_access(message):
        return
    
    stats = await db.get_statistics(message.from_user.id)
    
    if not stats:
        await message.answer("Ошибка при получении статистики.")
        return
    
    response = "📊 <b>Статистика</b>\n\n"
    response += f"👥 Всего клиентов: <b>{stats['total_clients']}</b>\n"
    response += f"⚠️ Просрочено платежей: <b>{stats['overdue_count']}</b>\n"
    response += f"📅 Платежей в этом месяце: <b>{stats['this_month_count']}</b>\n\n"
    
    # Financials
    if stats['overdue_amounts']:
        response += "🔴 <b>Общая задолженность:</b>\n"
        for currency, total in stats['overdue_amounts'].items():
            if total > 0:
                response += f"  • {utils.format_currency(total, currency)}\n"
        response += "\n"
        
    if stats['upcoming_amounts']:
        response += "� <b>Ожидается в течение 30 дней:</b>\n"
        for currency, total in stats['upcoming_amounts'].items():
            if total > 0:
                response += f"  • {utils.format_currency(total, currency)}\n"
        response += "\n"

    # Nearest payments
    if stats['nearest_payments']:
        response += "🕐 <b>Ближайшие оплаты:</b>\n"
        for p in stats['nearest_payments']:
            p_date = datetime.strptime(p['next_payment_date'], "%Y-%m-%d").date()
            days = utils.get_days_until(p_date)
            
            day_str = "сегодня" if days == 0 else (f"через {days} дн" if days > 0 else f"просрочено {abs(days)} дн")
            emoji = "🔴" if days < 0 else ("🟡" if days <= 3 else "🟢")
            
            response += f"{emoji} {p['name']}: {utils.format_currency(p['amount'], p['currency'])} ({day_str})\n"
    
    await message.answer(response, parse_mode="HTML")
    logger.info(f"User {message.from_user.id} viewed statistics")


# ============================================================================
# PAYMENT HISTORY
# ============================================================================

@router.message(F.text == "📜 История")
async def start_view_history(message: types.Message, state: FSMContext):
    """Start viewing payment history"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer("Нет клиентов для просмотра истории.")
        return
    
    await state.set_state(ViewHistory.selecting_client)
    await message.answer(
        "📜 <b>История платежей</b>\n\n"
        "Выберите клиента:",
        reply_markup=kb.get_client_list_keyboard(clients, "history"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("history_"))
async def show_client_history(callback: types.CallbackQuery, state: FSMContext):
    """Show payment history for selected client"""
    client_id = int(callback.data.split("_")[1])
    client = await db.get_client_by_id(client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    history = await db.get_payment_history(client_id, limit=20)
    
    response = f"📜 <b>История платежей</b>\n\n"
    response += f"👤 Клиент: <b>{client['name']}</b>\n\n"
    
    if history:
        for record in history:
            payment_date = datetime.strptime(record['payment_date'], "%Y-%m-%d").date()
            status_emoji = utils.get_status_emoji(record['status'])
            response += (
                f"{status_emoji} {utils.format_date(payment_date)} - "
                f"{utils.format_currency(record['amount'], record['currency'])}\n"
            )
            if record['notes']:
                response += f"   📝 {record['notes']}\n"
    else:
        response += "История платежей пуста."
    
    await callback.message.edit_text(response, parse_mode="HTML")
    await state.clear()
    await callback.answer()


# ============================================================================
# BACKUP
# ============================================================================


@router.message(F.text == "💾 Бэкап базы")
async def create_backup(message: types.Message):
    """Create database backup"""
    if not await utils.check_user_access(message):
        return
    
    await message.answer("⏳ Создание резервной копии...")
    
    backup_file = await db.create_backup()
    
    if backup_file:
        await message.answer(
            f"✅ <b>Резервная копия создана!</b>\n\n"
            f"📁 Файл: <code>{backup_file}</code>\n\n"
            f"Резервная копия сохранена в папке backups.",
            parse_mode="HTML"
        )
        logger.info(f"User {message.from_user.id} created backup: {backup_file}")
    else:
        await message.answer("❌ Ошибка при создании резервной копии.")


# ============================================================================
# EXPORT
# ============================================================================

@router.message(Command("export"))
async def export_data(message: types.Message):
    """Export data to CSV"""
    if not await utils.check_user_access(message):
        return
    
    clients = await db.get_clients(message.from_user.id)
    
    if not clients:
        await message.answer("Нет данных для экспорта.")
        return
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Имя', 'Сумма', 'Валюта', 'Следующий платеж', 'Интервал', 'Категория', 'Статус'])
    
    # Data
    for client in clients:
        interval_desc = utils.get_interval_description(client['interval_type'], client['interval_value'])
        writer.writerow([
            client['name'],
            client['amount'],
            client['currency'],
            client['next_payment_date'],
            interval_desc,
            client['category'] if 'category' in client.keys() else 'general',
            client['payment_status'] if 'payment_status' in client.keys() else 'pending'
        ])
    
    # Send as file
    csv_data = output.getvalue().encode('utf-8-sig')  # BOM for Excel
    file = types.BufferedInputFile(csv_data, filename=f"clients_{date.today()}.csv")
    
    await message.answer_document(
        file,
        caption="📊 Экспорт списка клиентов"
    )
    logger.info(f"User {message.from_user.id} exported {len(clients)} clients to CSV")

# ============================================================================
# SEARCH CLIENT
# ============================================================================

@router.message(F.text == "🔍 Поиск клиента")
async def start_search_client(message: types.Message, state: FSMContext):
    """Start searching for a client"""
    if not await utils.check_user_access(message):
        return
    
    await state.set_state(SearchClient.waiting_for_query)
    await message.answer(
        "🔍 <b>Поиск клиента</b>\n\n"
        "Введите имя клиента или часть заметки для поиска:",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(SearchClient.waiting_for_query)
async def process_search_query(message: types.Message, state: FSMContext):
    """Process search query"""
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("❌ Запрос слишком короткий. Введите хотя бы 2 символа.")
        return
    
    clients = await db.search_clients(message.from_user.id, query)
    
    if not clients:
        await message.answer(
            f"❌ Клиенты по запросу '<b>{query}</b>' не найдены.",
            reply_markup=kb.get_main_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    response = f"🔍 <b>Результаты поиска по запросу '{query}':</b>\n\n"
    
    for client in clients:
        response += utils.format_client_info(client, show_details=False) + "\n"
        
    await utils.send_long_message(message, response, parse_mode="HTML", reply_markup=kb.get_main_keyboard())
    
    # Also provide inline buttons to manage found clients
    await message.answer(
        "Выберите клиента для управления:",
        reply_markup=kb.get_client_list_keyboard(clients[:10], "search") # Limit to 10 for buttons to avoid huge list
    )
    
    await state.clear()


@router.callback_query(F.data.startswith("search_"))
async def process_search_selection(callback: types.CallbackQuery, state: FSMContext):
    """Process client selection from search results"""
    client_id = int(callback.data.split("_")[1])
    client = await db.get_client_by_id(client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"👤 <b>{client['name']}</b>\n"
        f"💰 Сделайте выбор:",
        reply_markup=kb.get_client_actions_keyboard(client_id),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================================================
# EXCEL EXPORT
# ============================================================================

@router.message(F.text == "📥 Скачать отчет (Excel)")
async def export_excel_report(message: types.Message):
    """Generate and send Excel report"""
    if not await utils.check_user_access(message):
        return
    
    # Notify user process started
    msg = await message.answer("⏳ Генерация отчета...")
    
    user_id = message.from_user.id
    clients = await db.get_clients(user_id)
    history = await db.get_all_payment_history(user_id)
    
    if not clients and not history:
        await msg.edit_text("❌ Нет данных для отчета.")
        return
    
    # Generate filename
    filename = f"report_{user_id}_{date.today()}.xlsx"
    
    # Create Excel file
    if utils.generate_excel_report(clients, history, filename):
        try:
            file = types.FSInputFile(filename)
            await message.answer_document(
                file,
                caption=f"📊 Итоговый отчет за {date.today()}"
            )
            logger.info(f"User {user_id} exported Excel report")
        except Exception as e:
            logger.error(f"Error sending Excel report: {e}")
            await msg.edit_text("❌ Ошибка при отправке файла.")
        finally:
            # Delete file
            if os.path.exists(filename):
                os.remove(filename)
                
        await msg.delete()
    else:
        await msg.edit_text("❌ Ошибка при создании отчета on server.")

