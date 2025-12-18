import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from config.settings import settings
from database.database import db
from bot.handlers import BotHandlers, REGISTRATION_USERNAME, REGISTRATION_NAME, REGISTRATION_CITY
from bot.handlers import ADD_REMINDER_TITLE, ADD_REMINDER_DESCRIPTION, ADD_REMINDER_TIME, ADD_REMINDER_RECURRENCE
from bot.handlers import EDIT_NAME, EDIT_CITY
from bot.group_handlers import GroupHandlers, CREATE_GROUP_NAME, CREATE_GROUP_DESCRIPTION, ADD_GROUP_REMINDER_TITLE, \
    ADD_GROUP_REMINDER_DESCRIPTION, ADD_GROUP_REMINDER_TIME
from utils.date_parser import DateParserService
from utils.reminder_scheduler import ReminderScheduler
from utils.timezone_service import TimezoneService
from weather.weather_service import WeatherService

logging.basicConfig(
    format='[%(asctime)s] [%(name)s]\t[%(levelname)s] : %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scheduler = ReminderScheduler()
weather_service = WeatherService()
timezone_service = TimezoneService()
date_parser = DateParserService()


async def main():
    logger.info("Initializing database...")
    db_initialized = await db.init_db()
    if not db_initialized:
        logger.error("Failed to initialize database")
        return

    logger.info("Creating Telegram bot application...")
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    bot_handlers = BotHandlers(weather_service, scheduler, timezone_service, date_parser)
    group_handlers = GroupHandlers(weather_service, scheduler, timezone_service, date_parser)

    reg_conv = ConversationHandler(
        entry_points=[CommandHandler('start', bot_handlers.start)],
        states={
            REGISTRATION_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.register_username)],
            REGISTRATION_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.register_name)],
            REGISTRATION_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.register_city)]
        },
        fallbacks=[CommandHandler('cancel', bot_handlers.cancel_registration)],
        per_user=True
    )

    reminder_conv = ConversationHandler(
        entry_points=[CommandHandler('add_reminder', bot_handlers.add_reminder_start)],
        states={
            ADD_REMINDER_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.add_reminder_title)],
            ADD_REMINDER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.add_reminder_description)],
            ADD_REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.add_reminder_time)],
            ADD_REMINDER_RECURRENCE: [CallbackQueryHandler(bot_handlers.add_reminder_recurrence, pattern='^rec_')]
        },
        fallbacks=[CommandHandler('cancel', bot_handlers.cancel_registration)],
        per_user=True
    )

    profile_edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot_handlers.profile_callback, pattern='^edit_')],
        states={
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.edit_name)],
            EDIT_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.edit_city)]
        },
        fallbacks=[CommandHandler('cancel', bot_handlers.cancel_registration)],
        per_user=True,
        allow_reentry=True
    )

    group_create_conv = ConversationHandler(
        entry_points=[CommandHandler('create_group', group_handlers.create_group_start)],
        states={
            CREATE_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_handlers.create_group_name)],
            CREATE_GROUP_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, group_handlers.create_group_description)]
        },
        fallbacks=[CommandHandler('cancel', bot_handlers.cancel_registration)],
        per_user=True
    )

    group_reminder_conv = ConversationHandler(
        entry_points=[CommandHandler('add_group_reminder', group_handlers.add_group_reminder_start)],
        states={
            ADD_GROUP_REMINDER_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, group_handlers.add_group_reminder_title)],
            ADD_GROUP_REMINDER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, group_handlers.add_group_reminder_description)],
            ADD_GROUP_REMINDER_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, group_handlers.add_group_reminder_time)]
        },
        fallbacks=[CommandHandler('cancel', bot_handlers.cancel_registration)],
        per_user=True
    )

    application.add_handler(reg_conv)
    application.add_handler(reminder_conv)
    application.add_handler(profile_edit_conv)
    application.add_handler(group_create_conv)
    application.add_handler(group_reminder_conv)

    application.add_handler(CallbackQueryHandler(bot_handlers.delete_reminder_callback, pattern='^del_rem_'))

    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('profile', bot_handlers.profile))
    application.add_handler(CommandHandler('my_reminders', bot_handlers.my_reminders))
    application.add_handler(CommandHandler('weather', bot_handlers.weather))

    application.add_handler(CommandHandler('my_groups', group_handlers.my_groups))
    application.add_handler(CommandHandler('invite_to_group', group_handlers.invite_to_group_start))
    application.add_handler(CommandHandler('group_message', group_handlers.send_group_message))
    application.add_handler(CommandHandler('leave_group', group_handlers.leave_group))
    application.add_handler(CommandHandler('group_info', group_handlers.group_info))

    application.add_handler(CommandHandler('user_info', bot_handlers.user_info))

    logger.info("Starting bot...")

    await application.initialize()

    scheduler.set_bot(application.bot)
    await scheduler.start()

    await application.start()
    await application.updater.start_polling()

    logger.info("Bot is running. Press Ctrl-C to stop.")

    stop_signal = asyncio.Event()
    try:
        await stop_signal.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Bot stopping...")
    finally:
        logger.info("Cleaning up...")
        await scheduler.stop()

        if application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()

        await db.close()
        logger.info("Bot stopped successfully.")

async def help_command(update, context):
    help_text = """
🤖 Умный Планировщик - Помощь

Команды:

📋 Регистрация и профиль:
/start - Начать регистрацию
/profile - Мой профиль

🔔 Напоминания:
/add_reminder - Добавить новое напоминание
/my_reminders - Мои напоминания

👥 Группы:
/create_group - Создать новую группу
/my_groups - Показать мои группы
/invite_to_group <group_id> <username> - Пригласить пользователя в группу
/group_message <group_id> <сообщение> - Отправить сообщение группе
/add_group_reminder <group_id> - Добавить напоминание всем участникам
/leave_group <group_id> - Покинуть группу
/group_info <group_id> - Информация о группе

🌤️ Погода:
/weather - Погода в вашем городе

❓ Помощь:
/help - Показать это сообщение

Примеры использования:
- Создание напоминания: /add_reminder
- Приглашение в группу: /invite_to_group 123 john_doe
- Отправка группового сообщения: /group_message 123 Всем привет!
- Изменение профиля: /profile -> выберите что хотите изменить
"""
    await update.message.reply_text(help_text)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)