import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime
import re
from database.database import db
from database.models import User, Reminder
from weather.weather_service import WeatherService
from utils.reminder_scheduler import ReminderScheduler
from utils.timezone_service import TimezoneService
from utils.date_parser import DateParserService
from sqlalchemy import select

# Conversation states
REGISTRATION_USERNAME, REGISTRATION_NAME, REGISTRATION_CITY = range(3)
ADD_REMINDER_TITLE, ADD_REMINDER_DESCRIPTION, ADD_REMINDER_TIME, ADD_REMINDER_RECURRENCE = range(4)

# Profile edit states
EDIT_NAME, EDIT_CITY = range(2)

class BotHandlers:
    def __init__(self,
                 weather_service: WeatherService,
                 scheduler: ReminderScheduler,
                 timezone_service: TimezoneService,
                 date_parser: DateParserService):
        self.weather_service = weather_service
        self.scheduler = scheduler
        self.timezone_service = timezone_service
        self.date_parser = date_parser

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=user.id)
            existing_user = await session.scalar(stmt)

            if existing_user:
                await update.message.reply_text(
                    f"Привет, {existing_user.name}! 👋\n"
                    f"Вы уже зарегистрированы в системе.\n\n"
                    f"Доступные команды:\n"
                    f"/add_reminder - Добавить напоминание\n"
                    f"/profile - Мой профиль\n"
                    f"/help - Помощь"
                )
                return ConversationHandler.END

        if user.username:
            async with db.get_session() as session:
                stmt = select(User).filter_by(username=user.username)
                existing_user = await session.scalar(stmt)
                if existing_user:
                    return REGISTRATION_USERNAME
                else:
                    context.user_data['username'] = user.username

                    if user.full_name:
                        context.user_data['name'] = user.full_name
                        await update.message.reply_text(
                            "Введите город, в котором вы живете (например, Москва):")
                        return REGISTRATION_CITY
                    else:
                        await update.message.reply_text("Введите ваше полное имя:")
                        return REGISTRATION_NAME

        await update.message.reply_text(
            "Добро пожаловать в Умный Планировщик! 👋\n"
            "Давайте зарегистрируемся. Придумайте себе уникальное имя пользователя (без @):"
        )
        return REGISTRATION_USERNAME

    async def register_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        username = update.message.text.strip()

        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
            await update.message.reply_text(
                "Имя пользователя должно содержать от 3 до 20 символов (латинские буквы, цифры, _).\n"
                "Попробуйте еще раз:"
            )
            return REGISTRATION_USERNAME

        async with db.get_session() as session:
            stmt = select(User).filter_by(username=username)
            existing_user = await session.scalar(stmt)
            if existing_user:
                await update.message.reply_text(
                    f"Пользователь с именем @{username} уже существует. Выберите другое имя:"
                )
                return REGISTRATION_USERNAME

        context.user_data['username'] = username
        await update.message.reply_text("Отлично! Теперь введите ваше полное имя:")
        return REGISTRATION_NAME

    async def register_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        name = update.message.text.strip()

        if len(name) < 2 or len(name) > 100:
            await update.message.reply_text("Имя должно быть от 2 до 100 символов. Попробуйте еще раз:")
            return REGISTRATION_NAME

        context.user_data['name'] = name
        await update.message.reply_text("Почти готово! Введите город, в котором вы живете (например, Москва):")
        return REGISTRATION_CITY

    async def register_city(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        city = update.message.text.strip()

        timezone_name = await self.timezone_service.get_timezone_by_city(city)
        if not timezone_name:
            await update.message.reply_text(
                f"Не удалось определить часовой пояс для города '{city}'.\n"
                f"Пожалуйста, введите название города более точно (на английском или русском):\n"
                f"(Например: 'Москва', 'Saint Petersburg' и т.п.)"
            )
            return REGISTRATION_CITY

        user_data = context.user_data
        user = update.effective_user

        new_user = User(
            telegram_id=user.id,
            username=user_data['username'],
            name=user_data['name'],
            city=city,
            timezone=timezone_name
        )

        async with db.get_session() as session:
            session.add(new_user)
            await session.commit()

        await update.message.reply_text(
            f"🎉 Поздравляю, {new_user.name}! Вы успешно зарегистрированы.\n"
            f"Ваш часовой пояс установлен как: {timezone_name}.\n\n"
            f"Теперь вы можете добавлять напоминания с помощью команды /add_reminder."
        )

        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text('Действие отменено.')
        context.user_data.clear()
        return ConversationHandler.END

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if not user:
                await update.message.reply_text("Вы не зарегистрированы. Используйте /start для регистрации.")
                return

            text = (
                f"👤 Ваш профиль:\n\n"
                f"ID: `{user.telegram_id}`\n"
                f"Имя: {user.name}\n"
                f"Имя пользователя: @{user.username}\n"
                f"Город: {user.city}\n"
                f"Часовой пояс: {user.timezone}\n"
                f"Дата регистрации: {user.created_at.strftime('%Y-%m-%d')}"
            )

            keyboard = [
                [InlineKeyboardButton("✏️ Изменить имя", callback_data='edit_name')],
                [InlineKeyboardButton("🏙️ Изменить город", callback_data='edit_city')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action = query.data.split('_')[1]
        if action == 'name':
            await query.edit_message_text("Введите новое имя:")
            return EDIT_NAME
        elif action == 'city':
            await query.edit_message_text("Введите новый город:")
            return EDIT_CITY
        return ConversationHandler.END

    async def edit_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_name = update.message.text.strip()

        if len(new_name) < 2 or len(new_name) > 100:
            await update.message.reply_text("Имя должно быть от 2 до 100 символов. Попробуйте еще раз:")
            return EDIT_NAME

        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if user:
                user.name = new_name
                await session.commit()
                await update.message.reply_text(f"✅ Ваше имя изменено на: {new_name}")
            else:
                await update.message.reply_text("Ошибка: Пользователь не найден.")

        return ConversationHandler.END

    async def edit_city(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_city = update.message.text.strip()

        timezone_name = await self.timezone_service.get_timezone_by_city(new_city)
        if not timezone_name:
            await update.message.reply_text(
                f"Не удалось определить часовой пояс для города '{new_city}'.\n"
                f"Попробуйте еще раз:"
            )
            return EDIT_CITY

        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if user:
                user.city = new_city
                user.timezone = timezone_name
                await session.commit()
                await update.message.reply_text(
                    f"✅ Ваш город и часовой пояс обновлены:\n"
                    f"Город: {new_city}\n"
                    f"Часовой пояс: {timezone_name}"
                )
            else:
                await update.message.reply_text("Ошибка: Пользователь не найден.")

        return ConversationHandler.END

    async def add_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if not user:
                await update.message.reply_text(
                    "Вы не зарегистрированы. Используйте /start для регистрации."
                )
                return ConversationHandler.END
            context.user_data['timezone'] = user.timezone

        await update.message.reply_text("Введите название (заголовок) напоминания:")
        return ADD_REMINDER_TITLE

    async def add_reminder_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        title = update.message.text.strip()

        if len(title) < 1 or len(title) > 200:
            await update.message.reply_text("Название должно быть от 1 до 200 символов. Попробуйте еще раз:")
            return ADD_REMINDER_TITLE

        context.user_data['title'] = title
        await update.message.reply_text("Введите описание (можно пропустить - skip):")
        return ADD_REMINDER_DESCRIPTION

    async def add_reminder_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        description = update.message.text.strip()
        if description == "skip":
            description = ""

        context.user_data['description'] = description

        user_tz = context.user_data.get('timezone', 'Europe/Minsk')

        await update.message.reply_text(
            f"🕒 Введите дату и время напоминания.\n"
            f"Вы можете использовать:\n"
            f"1. Естественный язык:\n"
            f"   - \"через 15 минут\"\n"
            f"   - \"завтра в 18:00\"\n"
            f"   - \"в пятницу в 9 утра\"\n"
            f"   - \"today at 5 pm\"\n"
            f"2. Точный формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            f"Ваш текущий часовой пояс: {user_tz}"
        )
        return ADD_REMINDER_TIME

    async def add_reminder_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        time_str = update.message.text.strip()
        user_tz_name = context.user_data['timezone']

        reminder_dt_utc_aware = None
        try:
            reminder_dt_local = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
            user_tz = pytz.timezone(user_tz_name)
            reminder_dt_local = user_tz.localize(reminder_dt_local)
            reminder_dt_utc_aware = reminder_dt_local.astimezone(pytz.utc)
        except ValueError:
            reminder_dt_utc_aware = self.date_parser.parse_natural_text(time_str, user_tz_name)

        if not reminder_dt_utc_aware or reminder_dt_utc_aware < datetime.now(pytz.utc):
            await update.message.reply_text("Некорректное время или время в прошлом. Попробуйте еще раз:")
            return ADD_REMINDER_TIME

        context.user_data['time_utc'] = reminder_dt_utc_aware

        keyboard = [
            [InlineKeyboardButton("Нет", callback_data='rec_none')],
            [InlineKeyboardButton("Ежедневно", callback_data='rec_daily')],
            [InlineKeyboardButton("Еженедельно", callback_data='rec_weekly')]
        ]
        await update.message.reply_text("Напоминание должно повторяться?", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_REMINDER_RECURRENCE

    async def add_reminder_recurrence(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        pattern_map = {
            'rec_none': None,
            'rec_daily': 'daily',
            'rec_weekly': 'weekly'
        }
        pattern = pattern_map.get(query.data)
        is_recurring = pattern is not None

        dt_utc = context.user_data['time_utc']
        dt_naive = dt_utc.replace(tzinfo=None)

        user_id = update.effective_user.id

        async with db.get_session() as session:
            new_reminder = Reminder(
                user_id=user_id,
                title=context.user_data['title'],
                description=context.user_data['description'],
                reminder_time=dt_naive,
                timezone=context.user_data['timezone'],
                is_recurring=is_recurring,
                recurring_pattern=pattern,
                is_sent=False
            )
            session.add(new_reminder)
            await session.commit()

        user_tz = pytz.timezone(context.user_data['timezone'])
        display_time = dt_utc.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')
        rec_text = "Без повтора" if not is_recurring else ("Ежедневно" if pattern == 'daily' else "Еженедельно")

        await query.edit_message_text(
            f"✅ Напоминание создано!\n"
            f"📌 {context.user_data['title']}\n"
            f"⏰ {display_time}\n"
            f"🔄 {rec_text}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    async def my_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        async with db.get_session() as session:
            stmt = select(Reminder).filter_by(user_id=user_id, is_sent=False).order_by(Reminder.reminder_time)
            reminders = (await session.scalars(stmt)).all()

            stmt_user = select(User).filter_by(telegram_id=user_id)
            user = await session.scalar(stmt_user)
            if not user: return

            user_tz = pytz.timezone(user.timezone)

            if not reminders:
                await update.message.reply_text("У вас нет активных напоминаний.")
                return

            await update.message.reply_text("🔔 Ваши активные напоминания:")

            for r in reminders:
                utc_aware = r.reminder_time.replace(tzinfo=pytz.utc)
                local_time = utc_aware.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')

                rec_info = ""
                if r.is_recurring:
                    rec_info = f"\n🔄 {r.recurring_pattern}"

                text = f"📌 *{r.title}*\n{r.description or ''}\n⏰ {local_time}{rec_info}"

                keyboard = [[InlineKeyboardButton("🗑️ Удалить", callback_data=f"del_rem_{r.id}")]]
                await update.message.reply_text(text, parse_mode='Markdown',
                                                reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_reminder_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        try:
            reminder_id = int(query.data.split('_')[2])

            success = await self.scheduler.cancel_reminder(reminder_id)

            if success:
                await query.edit_message_text("✅ Напоминание удалено.")
            else:
                await query.edit_message_text("⚠️ Напоминание уже удалено или не найдено.")

        except (IndexError, ValueError):
            await query.edit_message_text("Ошибка обработки команды.")

    async def weather(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if not user:
                await update.message.reply_text("Сначала /start")
                return

            weather_data = await self.weather_service.get_current_weather(user.city)
            time_of_day = self.weather_service.get_time_of_day()
            recommendation = await self.weather_service.get_weather_recommendation(user.city, time_of_day)

            if weather_data:
                text = f"🌤️ Погода в {user.city}: \n\n"
                text += f"🌡️ Температура: {weather_data['temperature']}°C\n"
                text += f"☁️ Описание: {weather_data['description']}\n"
                text += f"💧 Влажность: {weather_data['humidity']}%\n"
                text += f"💨 Скорость ветра: {weather_data['wind_speed']} м/с\n\n"

                if recommendation:
                    text += f"💡 Рекомендация: {recommendation}"
            else:
                text = (f"Не удалось получить данные о погоде для {user.city}. "
                        f"Проверьте правильность написания города (/profile для проверки).")

            await update.message.reply_text(text)

    async def user_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        username = context.args[0]
        async with db.get_session() as session:
            stmt = select(User).filter_by(username=username)
            user = await session.scalar(stmt)
            if user:
                message  = f"Пользователь:\n"
                message += f"Username: {user.username}\n"
                message += f"Telegram ID: {user.telegram_id}\n"
                message += f"Имя: {user.name}\n"
                message += f"Город: {user.city}\n"
                message += f"Часовой пояс: {user.timezone}\n"
                message += f"Дата регистрации: {user.created_at}"
            else:
                message = f"Пользователь @{username} не найден!"

        await update.message.reply_text(message)
