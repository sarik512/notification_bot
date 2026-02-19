from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from typing import List, Tuple


def get_main_keyboard():
    """Main menu keyboard"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить клиента"), KeyboardButton(text="🔍 Поиск клиента")],
            [KeyboardButton(text="📋 Список клиентов"), KeyboardButton(text="💰 Отметить оплату")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📥 Скачать отчет (Excel)")],
            [KeyboardButton(text="💾 Бэкап базы"), KeyboardButton(text="❌ Удалить клиента")]
        ],
        resize_keyboard=True
    )


def get_interval_type_keyboard():
    """Interval type selection keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Ежемесячно", callback_data="interval_monthly")],
        [InlineKeyboardButton(text="📆 Ежегодно", callback_data="interval_yearly")],
        [InlineKeyboardButton(text="📋 Еженедельно", callback_data="interval_weekly")],
    ])


def get_currency_keyboard():
    """Currency selection keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₽ RUB (Рубль)", callback_data="curr_RUB")],
        [InlineKeyboardButton(text="$ USD (Доллар)", callback_data="curr_USD")],
        [InlineKeyboardButton(text="🇺🇿 UZS (Сум)", callback_data="curr_UZS")],
    ])


def get_category_keyboard():
    """Category selection keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Бизнес", callback_data="cat_business")],
        [InlineKeyboardButton(text="👤 Личное", callback_data="cat_personal")],
        [InlineKeyboardButton(text="⭐ VIP", callback_data="cat_vip")],
        [InlineKeyboardButton(text="🧪 Тестовый", callback_data="cat_test")],
        [InlineKeyboardButton(text="📦 Общее", callback_data="cat_general")],
    ])


def get_cancel_keyboard():
    """Cancel operation keyboard"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


def get_payment_status_keyboard(client_id: int):
    """Payment status selection keyboard with quick actions"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплачено", callback_data=f"status_paid_{client_id}")],
        [InlineKeyboardButton(text="❌ Не оплачено", callback_data=f"status_unpaid_{client_id}")],
        [InlineKeyboardButton(text="⏰ Отложить на 3 дня", callback_data=f"status_postpone_3_{client_id}")],
        [InlineKeyboardButton(text="📅 Отложить на неделю", callback_data=f"status_postpone_7_{client_id}")],
        [InlineKeyboardButton(text="📆 Отложить на месяц", callback_data=f"status_postpone_30_{client_id}")],
    ])


def get_client_list_keyboard(clients: List, action_prefix: str = "select"):
    """Generate inline keyboard for client selection"""
    keyboard = []
    
    for client in clients:
        # Truncate name if too long
        name = client['name']
        if len(name) > 30:
            name = name[:27] + "..."
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{name} - {client['amount']} {client['currency']}",
                callback_data=f"{action_prefix}_{client['id']}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_options_keyboard(client_id: int):
    """Edit options keyboard for a client"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data=f"edit_name_{client_id}")],
        [InlineKeyboardButton(text="💰 Сумма", callback_data=f"edit_amount_{client_id}")],
        [InlineKeyboardButton(text="💱 Валюта", callback_data=f"edit_currency_{client_id}")],
        [InlineKeyboardButton(text="🔄 Интервал", callback_data=f"edit_interval_{client_id}")],
        [InlineKeyboardButton(text="📅 Дата платежа", callback_data=f"edit_date_{client_id}")],
        [InlineKeyboardButton(text="🏷️ Категория", callback_data=f"edit_category_{client_id}")],
        [InlineKeyboardButton(text="📝 Заметки", callback_data=f"edit_notes_{client_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_cancel")],
    ])


def get_confirmation_keyboard(action: str, item_id: int):
    """Confirmation keyboard for critical actions"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}_{item_id}")
        ]
    ])


def get_postpone_options_keyboard(client_id: int):
    """Postpone options keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ 1 день", callback_data=f"postpone_1_{client_id}")],
        [InlineKeyboardButton(text="3️⃣ 3 дня", callback_data=f"postpone_3_{client_id}")],
        [InlineKeyboardButton(text="7️⃣ Неделя", callback_data=f"postpone_7_{client_id}")],
        [InlineKeyboardButton(text="🗓️ 2 недели", callback_data=f"postpone_14_{client_id}")],
        [InlineKeyboardButton(text="📅 Месяц", callback_data=f"postpone_30_{client_id}")],
        [InlineKeyboardButton(text="📝 Указать дату", callback_data=f"postpone_custom_{client_id}")],
    ])


def get_filter_keyboard():
    """Filter keyboard for client list"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Просроченные", callback_data="filter_overdue")],
        [InlineKeyboardButton(text="🟡 Скоро (3 дня)", callback_data="filter_upcoming")],
        [InlineKeyboardButton(text="🟢 Все клиенты", callback_data="filter_all")],
        [InlineKeyboardButton(text="🏷️ По категориям", callback_data="filter_category")],
    ])


def get_export_keyboard():
    """Export options keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список клиентов (CSV)", callback_data="export_clients")],
        [InlineKeyboardButton(text="📜 История платежей (CSV)", callback_data="export_history")],
        [InlineKeyboardButton(text="📊 Полный отчет", callback_data="export_full")],
    ])


def get_back_to_main_keyboard():
    """Simple back to main menu button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])


def get_client_actions_keyboard(client_id: int):
    """Actions for a specific client selected from search"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Отметить оплату", callback_data=f"pay_{client_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{client_id}")],
        [InlineKeyboardButton(text="📜 История", callback_data=f"history_{client_id}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_{client_id}")],
    ])
