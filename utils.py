"""Utility functions for the bot"""
from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from aiogram import types
from config import Config
from logger import logger


async def check_user_access(message: types.Message) -> bool:
    """Check if user has access to the bot"""
    user_id = message.from_user.id
    
    if not Config.is_user_allowed(user_id):
        await message.answer(
            "⛔ <b>Доступ запрещен</b>\n\n"
            "У вас нет прав для использования этого бота.\n"
            f"Ваш ID: <code>{user_id}</code>\n\n"
            "Обратитесь к администратору бота для получения доступа.",
            parse_mode="HTML"
        )
        logger.warning(f"Unauthorized access attempt from user {user_id} (@{message.from_user.username})")
        return False
    
    return True


def parse_date(date_str: str) -> Optional[date]:
    """Parse date from string in DD.MM.YYYY format"""
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def format_date(date_obj: date) -> str:
    """Format date to DD.MM.YYYY"""
    return date_obj.strftime("%d.%m.%Y")


def format_currency(amount: float, currency: str = "RUB") -> str:
    """Format currency with symbol"""
    symbols = {
        "RUB": "₽",
        "USD": "$",
        "UZS": "сум"
    }
    symbol = symbols.get(currency, currency)
    return f"{amount:,.2f} {symbol}"


def get_days_until(target_date: date) -> int:
    """Get number of days until target date (negative if overdue)"""
    return (target_date - date.today()).days


def get_status_emoji(payment_status: str) -> str:
    """Get emoji for payment status"""
    status_map = {
        'pending': '⏳',
        'paid': '✅',
        'unpaid': '❌',
        'overdue': '⚠️'
    }
    return status_map.get(payment_status, '❓')


def format_client_info(client, show_details: bool = True) -> str:
    """Format client information for display"""
    from datetime import datetime
    
    next_payment = datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()
    days_until = get_days_until(next_payment)
    
    # Determine status
    if days_until < 0:
        status = f"⚠️ Просрочено на {abs(days_until)} дн."
        status_emoji = "🔴"
    elif days_until == 0:
        status = "📅 Сегодня"
        status_emoji = "🟡"
    elif days_until <= 3:
        status = f"⏰ Через {days_until} дн."
        status_emoji = "🟡"
    else:
        status = f"✅ Через {days_until} дн."
        status_emoji = "🟢"
    
    # Interval description
    interval_map = {
        'monthly': 'месяц',
        'weekly': 'неделя',
        'yearly': 'год'
    }
    interval_word = interval_map.get(client['interval_type'], client['interval_type'])
    
    if client['interval_value'] == 1:
        interval_text = f"Каждый {interval_word}"
    else:
        interval_text = f"Каждые {client['interval_value']} {interval_word}"
    
    info = (
        f"{status_emoji} <b>{client['name']}</b>\n"
        f"💰 Сумма: {format_currency(client['amount'], client['currency'])}\n"
        f"📅 Следующий платеж: {format_date(next_payment)}\n"
        f"📊 Статус: {status}\n"
    )
    
    if show_details:
        info += f"🔄 Интервал: {interval_text}\n"
        if client.get('category') and client['category'] != 'general':
            info += f"🏷️ Категория: {client['category']}\n"
        if client.get('notes'):
            info += f"📝 Заметки: {client['notes']}\n"
    
    return info


def validate_amount(amount_str: str) -> Tuple[bool, Optional[float], str]:
    """Validate and parse amount string"""
    try:
        amount = float(amount_str.replace(',', '.').strip())
        if amount <= 0:
            return False, None, "Сумма должна быть больше нуля"
        if amount > 1_000_000_000:
            return False, None, "Сумма слишком большая"
        return True, amount, ""
    except ValueError:
        return False, None, "Неверный формат суммы. Используйте числа, например: 5000 или 5000.50"


def validate_interval_value(value_str: str) -> Tuple[bool, Optional[int], str]:
    """Validate interval value"""
    try:
        value = int(value_str.strip())
        if value <= 0:
            return False, None, "Значение должно быть больше нуля"
        if value > 100:
            return False, None, "Значение слишком большое (максимум 100)"
        return True, value, ""
    except ValueError:
        return False, None, "Неверный формат. Введите целое число, например: 1, 2, 3"


def get_interval_description(interval_type: str, interval_value: int) -> str:
    """Get human-readable interval description"""
    interval_map = {
        'monthly': ('месяц', 'месяца', 'месяцев'),
        'weekly': ('неделю', 'недели', 'недель'),
        'yearly': ('год', 'года', 'лет')
    }
    
    if interval_type not in interval_map:
        return f"{interval_value} {interval_type}"
    
    words = interval_map[interval_type]
    
    if interval_value == 1:
        return f"Каждый {words[0]}"
    elif interval_value % 10 == 1 and interval_value % 100 != 11:
        return f"Каждый {interval_value} {words[0]}"
    elif 2 <= interval_value % 10 <= 4 and (interval_value % 100 < 10 or interval_value % 100 >= 20):
        return f"Каждые {interval_value} {words[1]}"
    else:
        return f"Каждые {interval_value} {words[2]}"


async def send_long_message(message: types.Message, text: str, **kwargs):
    """Send long message, splitting if necessary"""
    max_length = 4096
    
    if len(text) <= max_length:
        await message.answer(text, **kwargs)
    else:
        # Split by lines
        lines = text.split('\n')
        current_message = ""
        
        for line in lines:
            if len(current_message) + len(line) + 1 <= max_length:
                current_message += line + '\n'
            else:
                if current_message:
                    await message.answer(current_message, **kwargs)
                current_message = line + '\n'
        
        if current_message:
            await message.answer(current_message, **kwargs)


def generate_excel_report(clients: list, history: list, filename: str) -> bool:
    """Generate Excel report with clients and payment history"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        
        wb = Workbook()
        
        # --- Clients Sheet ---
        ws_clients = wb.active
        ws_clients.title = "Клиенты"
        
        # Headers
        headers = ["ID", "Имя", "Сумма", "Валюта", "Категория", "Интервал", "След. платеж", "Заметки"]
        for col, header in enumerate(headers, 1):
            cell = ws_clients.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            
        # Data
        for row, client in enumerate(clients, 2):
            ws_clients.cell(row=row, column=1, value=client['id'])
            ws_clients.cell(row=row, column=2, value=client['name'])
            ws_clients.cell(row=row, column=3, value=client['amount'])
            ws_clients.cell(row=row, column=4, value=client['currency'])
            ws_clients.cell(row=row, column=5, value=client['category'])
            
            # Format interval
            interval = f"{client['interval_value']} {client['interval_type']}"
            ws_clients.cell(row=row, column=6, value=interval)
            
            ws_clients.cell(row=row, column=7, value=client['next_payment_date'])
            ws_clients.cell(row=row, column=8, value=client['notes'])
            
        # Adjust column widths
        for col in range(1, 9):
            ws_clients.column_dimensions[chr(64 + col)].width = 15
        ws_clients.column_dimensions['B'].width = 30  # Name
        ws_clients.column_dimensions['H'].width = 40  # Notes
            
        # --- History Sheet ---
        ws_history = wb.create_sheet("История платежей")
        
        # Headers
        headers = ["Дата", "Клиент", "Сумма", "Валюта", "Статус", "Заметки"]
        for col, header in enumerate(headers, 1):
            cell = ws_history.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            
        # Data
        for row, item in enumerate(history, 2):
            ws_history.cell(row=row, column=1, value=item['payment_date'])
            # Check if client_name exists (joined query)
            name = item['client_name'] if 'client_name' in item.keys() else f"Client {item['client_id']}"
            ws_history.cell(row=row, column=2, value=name)
            ws_history.cell(row=row, column=3, value=item['amount'])
            ws_history.cell(row=row, column=4, value=item['currency'])
            ws_history.cell(row=row, column=5, value=item['status'])
            ws_history.cell(row=row, column=6, value=item['notes'])
            
        # Adjust column widths
        for col in range(1, 7):
            ws_history.column_dimensions[chr(64 + col)].width = 15
        ws_history.column_dimensions['B'].width = 30  # Client
        ws_history.column_dimensions['F'].width = 40  # Notes
        
        wb.save(filename)
        return True
    except Exception as e:
        logger.error(f"Error generating Excel report: {e}")
        return False
