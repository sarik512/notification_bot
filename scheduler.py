from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
import database as db
from datetime import date, timedelta
from config import Config
from logger import logger
import keyboards as kb
import utils


scheduler = AsyncIOScheduler()


async def check_payments(bot: Bot):
    """Check for due payments and send reminders"""
    logger.info("Starting payment check...")
    
    try:
        # Get due payments (today or overdue)
        due_payments = await db.get_due_payments()
        
        # Get upcoming payments (advance notification)
        upcoming_payments = await db.get_upcoming_payments(Config.ADVANCE_NOTIFICATION_DAYS)
        
        logger.info(f"Found {len(due_payments)} due payments and {len(upcoming_payments)} upcoming payments")
        
        # Process due/overdue payments
        for client in due_payments:
            await send_payment_reminder(bot, client, is_overdue=True)
        
        # Process upcoming payments (advance notification)
        for client in upcoming_payments:
            await send_advance_notification(bot, client)
        
        logger.info("Payment check completed successfully")
        
    except Exception as e:
        logger.error(f"Error during payment check: {e}", exc_info=True)


async def send_payment_reminder(bot: Bot, client, is_overdue: bool = False):
    """Send payment reminder to user"""
    try:
        user_id = client['user_id']
        name = client['name']
        amount = client['amount']
        currency = client['currency']
        payment_status = client.get('payment_status', 'pending')
        next_payment_date = client['next_payment_date']
        
        # Parse date
        from datetime import datetime
        next_payment = datetime.strptime(next_payment_date, "%Y-%m-%d").date()
        today = date.today()
        days_overdue = (today - next_payment).days
        
        # Determine message type
        if days_overdue == 0:
            # Payment is due today
            emoji = "🔔"
            title = "НАПОМИНАНИЕ О ПЛАТЕЖЕ"
            status_line = f"📅 Дата платежа: <b>СЕГОДНЯ</b> ({utils.format_date(next_payment)})"
            color = "🟡"
        elif days_overdue > 0:
            # Payment is overdue
            emoji = "⚠️"
            title = "ПРОСРОЧЕННЫЙ ПЛАТЁЖ"
            status_line = f"📅 Дата платежа: {utils.format_date(next_payment)}\n⏰ Просрочено на: <b>{days_overdue} дн.</b>"
            color = "🔴"
        else:
            # Future payment (shouldn't happen in this function)
            return
        
        # Build message
        message = (
            f"{emoji} <b>{title}</b> {color}\n\n"
            f"👤 Клиент: <b>{name}</b>\n"
            f"💰 Сумма: <b>{utils.format_currency(amount, currency)}</b>\n"
            f"{status_line}\n"
        )
        
        if days_overdue > 0:
            status_text = {
                'unpaid': '❌ Не оплачено',
                'pending': '⏳ Ожидает оплаты',
                'paid': '✅ Оплачено'
            }
            message += f"📊 Статус: {status_text.get(payment_status, '⏳ Ожидает оплаты')}\n"
        
        message += "\n💡 Используйте '💰 Отметить оплату' когда клиент оплатит."
        
        # Send message with quick action buttons
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            reply_markup=kb.get_payment_status_keyboard(client['id'])
        )
        
        logger.info(f"Sent payment reminder to user {user_id} for client '{name}' (overdue: {days_overdue} days)")
        
    except Exception as e:
        logger.error(f"Failed to send payment reminder to user {client.get('user_id')}: {e}")


async def send_advance_notification(bot: Bot, client):
    """Send advance notification for upcoming payment"""
    try:
        user_id = client['user_id']
        name = client['name']
        amount = client['amount']
        currency = client['currency']
        next_payment_date = client['next_payment_date']
        
        # Parse date
        from datetime import datetime
        next_payment = datetime.strptime(next_payment_date, "%Y-%m-%d").date()
        days_until = utils.get_days_until(next_payment)
        
        # Build message
        message = (
            f"📢 <b>ПРЕДСТОЯЩИЙ ПЛАТЁЖ</b> 🟡\n\n"
            f"👤 Клиент: <b>{name}</b>\n"
            f"💰 Сумма: <b>{utils.format_currency(amount, currency)}</b>\n"
            f"📅 Дата платежа: {utils.format_date(next_payment)}\n"
            f"⏰ Осталось: <b>{days_until} дн.</b>\n\n"
            f"💡 Не забудьте напомнить клиенту о платеже!"
        )
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML"
        )
        
        logger.info(f"Sent advance notification to user {user_id} for client '{name}' ({days_until} days)")
        
    except Exception as e:
        logger.error(f"Failed to send advance notification to user {client.get('user_id')}: {e}")


async def send_daily_summary(bot: Bot):
    """Send daily summary to all users (optional feature)"""
    try:
        logger.info("Sending daily summaries...")
        
        # This would require getting all unique user IDs
        # For now, we'll skip this as it requires additional database queries
        # Can be implemented later if needed
        
        logger.info("Daily summaries sent")
        
    except Exception as e:
        logger.error(f"Error sending daily summaries: {e}", exc_info=True)


def setup_scheduler(bot: Bot):
    """Setup scheduler with all jobs"""
    try:
        # Main payment check job - runs daily at configured time
        scheduler.add_job(
            check_payments,
            'cron',
            hour=Config.CHECK_TIME_HOUR,
            minute=Config.CHECK_TIME_MINUTE,
            args=[bot],
            id='check_payments',
            replace_existing=True
        )
        
        logger.info(
            f"Scheduled payment checks at {Config.CHECK_TIME_HOUR:02d}:{Config.CHECK_TIME_MINUTE:02d} daily"
        )
        
        # Optional: Daily summary at 9:00 AM
        # scheduler.add_job(
        #     send_daily_summary,
        #     'cron',
        #     hour=9,
        #     minute=0,
        #     args=[bot],
        #     id='daily_summary',
        #     replace_existing=True
        # )
        
        # For testing: check every minute (uncomment to enable)
        # WARNING: Only use for testing!
        # scheduler.add_job(
        #     check_payments,
        #     'interval',
        #     minutes=1,
        #     args=[bot],
        #     id='check_payments_test',
        #     replace_existing=True
        # )
        # logger.warning("TESTING MODE: Payment checks running every minute!")
        
        scheduler.start()
        logger.info("Scheduler started successfully")
        
    except Exception as e:
        logger.error(f"Error setting up scheduler: {e}", exc_info=True)
        raise


def stop_scheduler():
    """Stop the scheduler gracefully"""
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
