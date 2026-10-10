import asyncio
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
import database as db
from config import Config
from logger import logger
import keyboards as kb
import utils


scheduler = AsyncIOScheduler()

# Telegram allows ~30 messages/second overall; stay comfortably below it
SEND_INTERVAL = 0.05


async def _send(bot: Bot, user_id: int, text: str, reply_markup=None) -> bool:
    """Send a message, riding out flood limits. Returns True if delivered."""
    for _ in range(3):
        try:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
            await asyncio.sleep(SEND_INTERVAL)
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"Flood limit hit, retrying in {e.retry_after}s")
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            logger.warning(f"User {user_id} blocked the bot or deleted the chat, skipping")
            return False
        except TelegramAPIError as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            return False
    logger.error(f"Gave up sending to user {user_id} after repeated flood limits")
    return False


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
            await send_payment_reminder(bot, client)

        # Process upcoming payments (advance notification)
        for client in upcoming_payments:
            await send_advance_notification(bot, client)

        logger.info("Payment check completed successfully")

    except Exception as e:
        logger.error(f"Error during payment check: {e}", exc_info=True)


async def send_payment_reminder(bot: Bot, client):
    """Send reminder for a payment that is due today or overdue"""
    try:
        next_payment = datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()
        days_overdue = (date.today() - next_payment).days

        if days_overdue == 0:
            emoji, title, color = "🔔", "НАПОМИНАНИЕ О ПЛАТЕЖЕ", "🟡"
            status_line = f"📅 Дата платежа: <b>СЕГОДНЯ</b> ({utils.format_date(next_payment)})"
        elif days_overdue > 0:
            emoji, title, color = "⚠️", "ПРОСРОЧЕННЫЙ ПЛАТЁЖ", "🔴"
            status_line = (
                f"📅 Дата платежа: {utils.format_date(next_payment)}\n"
                f"⏰ Просрочено на: <b>{days_overdue} дн.</b>"
            )
        else:
            # Future payment (shouldn't happen in this function)
            return

        message = (
            f"{emoji} <b>{title}</b> {color}\n\n"
            f"👤 Клиент: <b>{utils.esc(client['name'])}</b>\n"
            f"💰 Сумма: <b>{utils.format_currency(client['amount'], client['currency'])}</b>\n"
            f"{status_line}\n"
        )

        if days_overdue > 0:
            status_text = {
                'unpaid': '❌ Не оплачено',
                'pending': '⏳ Ожидает оплаты',
                'paid': '✅ Оплачено'
            }
            message += f"📊 Статус: {status_text.get(client['payment_status'], '⏳ Ожидает оплаты')}\n"

        message += "\n💡 Используйте '💰 Отметить оплату' когда клиент оплатит."

        if await _send(bot, client['user_id'], message, kb.get_payment_status_keyboard(client['id'])):
            logger.info(
                f"Sent payment reminder to user {client['user_id']} "
                f"for client '{client['name']}' (overdue: {days_overdue} days)"
            )

    except Exception as e:
        logger.error(f"Failed to build payment reminder for client {client['id']}: {e}")


async def send_advance_notification(bot: Bot, client):
    """Send advance notification for upcoming payment"""
    try:
        next_payment = datetime.strptime(client['next_payment_date'], "%Y-%m-%d").date()
        days_until = utils.get_days_until(next_payment)

        message = (
            f"📢 <b>ПРЕДСТОЯЩИЙ ПЛАТЁЖ</b> 🟡\n\n"
            f"👤 Клиент: <b>{utils.esc(client['name'])}</b>\n"
            f"💰 Сумма: <b>{utils.format_currency(client['amount'], client['currency'])}</b>\n"
            f"📅 Дата платежа: {utils.format_date(next_payment)}\n"
            f"⏰ Осталось: <b>{days_until} дн.</b>\n\n"
            f"💡 Не забудьте напомнить клиенту о платеже!"
        )

        if await _send(bot, client['user_id'], message):
            logger.info(
                f"Sent advance notification to user {client['user_id']} "
                f"for client '{client['name']}' ({days_until} days)"
            )

    except Exception as e:
        logger.error(f"Failed to build advance notification for client {client['id']}: {e}")


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
            replace_existing=True,
            # The default grace period is 1 second: a run that starts late (busy
            # event loop, or a restart right around the scheduled time) would be
            # skipped silently and nobody would get reminders that day.
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1
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
