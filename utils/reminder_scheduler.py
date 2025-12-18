import asyncio
from datetime import datetime, timedelta
from telegram import Bot
from telegram.error import TelegramError
from database.database import db
from database.models import Reminder, User
from weather.weather_service import WeatherService
from utils.timezone_service import TimezoneService
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import pytz
import logging

logger = logging.getLogger(__name__)

class ReminderScheduler:
    def __init__(self):
        self.bot = None
        self.weather_service = WeatherService()
        self.timezone_service = TimezoneService()
        self.running = False

    def set_bot(self, bot: Bot):
        self.bot = bot

    async def start(self):
        if self.running:
            return

        if not self.bot:
            raise RuntimeError("Bot instance must be set using set_bot() before starting the scheduler.")

        self.running = True
        logger.info("Reminder scheduler started")

        asyncio.create_task(self.reminder_check_loop())

    async def stop(self):
        self.running = False
        logger.info("Reminder scheduler stopped")

    async def reminder_check_loop(self):
        while self.running:
            try:
                now_utc = datetime.now(pytz.utc).replace(tzinfo=None)

                async with db.get_session() as session:
                    await session.commit()

                    stmt = select(Reminder).filter_by(
                        is_sent=False
                    ).filter(
                        Reminder.reminder_time <= now_utc
                    )

                    due_reminders = await session.scalars(stmt)
                    due_reminders_list = due_reminders.all()

                    if due_reminders_list:
                        logger.info(f"Processing {len(due_reminders_list)} reminders at {now_utc}...")

                    for reminder in due_reminders_list:
                        r_id = reminder.id
                        u_id = reminder.user_id
                        asyncio.create_task(self.process_reminder(r_id, u_id))

            except Exception as e:
                logger.error(f"Error in reminder check loop: {e}")

            await asyncio.sleep(60)

    async def process_reminder(self, reminder_id: int, user_id: int):
        try:
            await self.send_reminder_message(reminder_id, user_id)
        except Exception as e:
            logger.error(f"Error sending message for reminder {reminder_id}: {e}")

        try:
            async with db.get_session() as session:
                reminder = await session.get(Reminder, reminder_id)
                if not reminder:
                    return

                if reminder.is_recurring and reminder.recurring_pattern:
                    await self.handle_recurrence(session, reminder)
                else:
                    reminder.is_sent = True

                await session.commit()

        except Exception as e:
            logger.error(f"Error updating DB for reminder {reminder_id}: {e}")

    async def handle_recurrence(self, session, reminder: Reminder):
        try:
            old_time = reminder.reminder_time
            new_time = None

            if reminder.recurring_pattern == 'daily':
                new_time = old_time + timedelta(days=1)
            elif reminder.recurring_pattern == 'weekly':
                new_time = old_time + timedelta(weeks=1)
            elif reminder.recurring_pattern == 'monthly':
                new_time = old_time + timedelta(days=30)

            if new_time:
                new_reminder = Reminder(
                    user_id=reminder.user_id,
                    title=reminder.title,
                    description=reminder.description,
                    reminder_time=new_time,
                    timezone=reminder.timezone,
                    is_recurring=True,
                    recurring_pattern=reminder.recurring_pattern,
                    is_sent=False
                )
                session.add(new_reminder)
                logger.info(f"Rescheduled reminder {reminder.id} to {new_time}")

            reminder.is_sent = True

        except Exception as e:
            logger.error(f"Error rescheduling reminder {reminder.id}: {e}")

    async def send_reminder_message(self, reminder_id: int, user_id: int):
        async with db.get_session() as session:
            stmt = select(Reminder).options(selectinload(Reminder.user)).filter_by(id=reminder_id)
            reminder = await session.scalar(stmt)

            if not reminder:
                logger.error(f"Reminder {reminder_id} not found.")
                return

            user = reminder.user

            if not user:
                stmt_user = select(User).filter_by(telegram_id=user_id)
                user = await session.scalar(stmt_user)

                if not user:
                    logger.error(f"User {user_id} not found for reminder {reminder_id}.")
                    return

            weather_data = None
            recommendation = ""
            try:
                weather_data = await self.weather_service.get_current_weather(user.city)
                if weather_data:
                    time_of_day = self.weather_service.get_time_of_day()
                    recommendation = await self.weather_service.get_weather_recommendation(user.city, time_of_day)
            except Exception as e:
                logger.error(f"Weather error for {user.city}: {e}")

            message = f"🔔 *Напоминание: {reminder.title}*\n\n"
            if reminder.description:
                message += f"{reminder.description}\n\n"

            try:
                reminder_time_utc_aware = reminder.reminder_time.replace(tzinfo=pytz.utc)
                local_time = reminder_time_utc_aware.astimezone(pytz.timezone(reminder.timezone))
                message += f"Время: {local_time.strftime('%d.%m.%Y %H:%M')} ({reminder.timezone})\n"
            except Exception:
                message += f"Время: {reminder.reminder_time} (UTC)\n"

            if weather_data:
                message += f"\n🌤️ Погода в {user.city}: \n"
                message += f"🌡️ {weather_data['temperature']}°C\n"
                message += f"☁️ {weather_data['description']}\n"

            if recommendation:
                message += f"\n💡 {recommendation}"

            if reminder.is_recurring:
                message += f"\n\n🔄 Повтор: {self.translate_pattern(reminder.recurring_pattern)}"

            try:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except TelegramError as e:
                logger.error(f"Telegram error sending to {user.telegram_id}: {e}")

    def translate_pattern(self, pattern):
        mapping = {
            'daily': 'Ежедневно',
            'weekly': 'Еженедельно',
            'monthly': 'Ежемесячно'
        }
        return mapping.get(pattern, pattern)

    async def cancel_reminder(self, reminder_id: int):
        try:
            async with db.get_session() as session:
                reminder = await session.get(Reminder, reminder_id)
                if reminder:
                    await session.delete(reminder)
                    await session.commit()
                    logger.info(f"Deleted reminder {reminder_id}")
                    return True
        except Exception as e:
            logger.error(f"Error canceling reminder {reminder_id}: {e}")
            return False
        return False