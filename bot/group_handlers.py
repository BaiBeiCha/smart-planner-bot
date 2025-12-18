from tokenize import group

from database.models import Group, GroupMember, User
import pytz
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime
from database.database import db
from database.models import User, Reminder
from weather.weather_service import WeatherService
from utils.reminder_scheduler import ReminderScheduler
from utils.timezone_service import TimezoneService
from utils.date_parser import DateParserService
from sqlalchemy import select

# Conversation states for group creation
CREATE_GROUP_NAME, CREATE_GROUP_DESCRIPTION = range(2)

# Conversation states for group reminder
ADD_GROUP_REMINDER_TITLE, ADD_GROUP_REMINDER_DESCRIPTION, ADD_GROUP_REMINDER_TIME = range(3)

class GroupHandlers:
    def __init__(self,
                 weather_service: WeatherService,
                 scheduler: ReminderScheduler,
                 timezone_service: TimezoneService,
                 date_parser: DateParserService):
        self.weather_service = weather_service
        self.scheduler = scheduler
        self.timezone_service = timezone_service
        self.date_parser = date_parser

    async def create_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            user = await session.scalar(stmt)
            if not user:
                await update.message.reply_text(
                    "Вы не зарегистрированы. Используйте /start для регистрации."
                )
                return ConversationHandler.END

        await update.message.reply_text("Введите название группы:")
        return CREATE_GROUP_NAME

    async def create_group_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        name = update.message.text.strip()

        if len(name) < 1 or len(name) > 100:
            await update.message.reply_text(
                "Название группы должно быть от 1 до 100 символов.\n"
                "Попробуйте еще раз:"
            )
            return CREATE_GROUP_NAME

        context.user_data['group_name'] = name
        await update.message.reply_text("Введите описание группы (можно пропустить - skip):")
        return CREATE_GROUP_DESCRIPTION

    async def create_group_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        description = update.message.text.strip()
        if description == "skip":
            description = ""
        user_id = update.effective_user.id

        async with db.get_session() as session:
            new_group = Group(
                name=context.user_data['group_name'],
                description=description,
                creator_id=user_id
            )
            session.add(new_group)
            await session.flush()

            new_member = GroupMember(
                group_id=new_group.id,
                user_id=user_id,
                is_admin=True
            )
            session.add(new_member)

            await session.commit()

            await update.message.reply_text(
                f"🎉 Группа '{new_group.name}' успешно создана!\n"
                f"ID группы: `{new_group.id}`. Используйте этот ID для приглашения других участников (/invite_to_group)."
            )

        context.user_data.clear()
        return ConversationHandler.END

    async def my_groups(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        async with db.get_session() as session:
            stmt = select(GroupMember).filter_by(
                user_id=user_id
            )
            memberships = await session.scalars(stmt)
            memberships = memberships.all()

            if not memberships:
                await update.message.reply_text("Вы не состоите ни в одной активной группе.")
                return

            text = "👥 Ваши группы:\n\n"
            group_list = []

            for membership in memberships:
                group = await session.get(Group, membership.group_id)
                if group and group.is_active:
                    role = "Администратор" if membership.is_admin else "Участник"
                    group_list.append(
                        f"*{group.name}* (ID: `{group.id}`)\n"
                        f"  Роль: {role}"
                    )

            if not group_list:
                await update.message.reply_text("Вы не состоите ни в одной активной группе.")
                return

            text += "\n\n".join(group_list)
            await update.message.reply_text(text, parse_mode='Markdown')

    async def invite_to_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) != 2:
            await update.message.reply_text(
                "Использование: /invite_to_group <group_id> <username>\n"
                "Например: /invite_to_group 123 john_doe"
            )
            return

        try:
            group_id = int(args[0])
            username = args[1].lstrip('@')
        except ValueError:
            await update.message.reply_text("ID группы должен быть числом.")
            return

        async with db.get_session() as session:
            group = await session.get(Group, group_id)
            if not group or not group.is_active:
                await update.message.reply_text(f"Группа с ID {group_id} не найдена или неактивна.")
                return

            stmt_admin = select(GroupMember).filter_by(
                group_id=group_id,
                user_id=update.effective_user.id
            )
            membership = await session.scalar(stmt_admin)

            if not membership or not membership.is_admin:
                await update.message.reply_text("Только администраторы могут приглашать в эту группу.")
                return

            stmt_user = select(User).filter_by(username=username)
            invited_user = await session.scalar(stmt_user)
            if not invited_user:
                await update.message.reply_text(f"Пользователь @{username} не найден.")
                return

            stmt_existing = select(GroupMember).filter_by(
                group_id=group_id,
                user_id=invited_user.telegram_id
            )
            existing_membership = await session.scalar(stmt_existing)

            if existing_membership:
                await update.message.reply_text(f"Пользователь @{username} уже состоит в группе '{group.name}'.")
                return

            new_member = GroupMember(
                group_id=group_id,
                user_id=invited_user.telegram_id,
                is_admin=False
            )
            session.add(new_member)
            await session.commit()

            await update.message.reply_text(
                f"✅ Пользователь @{username} успешно приглашен и добавлен в группу '{group.name}'."
            )

            try:
                await context.bot.send_message(
                    chat_id=invited_user.telegram_id,
                    text=f"🎉 Вы были добавлены в группу *'{group.name}'*!",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Error notifying invited user {invited_user.telegram_id}: {e}")

    async def send_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /group_message <group_id> <сообщение>\n"
                "Например: /group_message 123 Всем привет!"
            )
            return

        try:
            group_id = int(args[0])
            message = " ".join(args[1:])
        except ValueError:
            await update.message.reply_text("ID группы должен быть числом.")
            return

        async with db.get_session() as session:
            stmt_membership = select(GroupMember).filter_by(
                group_id=group_id,
                user_id=update.effective_user.id
            )
            membership = await session.scalar(stmt_membership)

            if not membership:
                await update.message.reply_text("Вы не состоите в этой группе и не можете отправлять сообщения.")
                return

            group_entity = await session.get(Group, group_id)
            if not group_entity or not group_entity.is_active:
                await update.message.reply_text(f"Группа с ID {group_id} не найдена или неактивна.")
                return

            stmt_members = select(GroupMember).filter_by(
                group_id=group_id
            )
            members = await session.scalars(stmt_members)
            members = members.all()

            stmt = select(User).filter_by(telegram_id=update.effective_user.id)
            sender_user = await session.scalar(stmt)
            sender_name = f"{sender_user.name} @{sender_user.username}" if sender_user else 'Неизвестный'

            sent_count = 0
            for member in members:
                if member.user_id != update.effective_user.id:
                    try:
                        await context.bot.send_message(
                            chat_id=member.user_id,
                            text=f"📢 Сообщение от {sender_name} в группе *'{group_entity.name}'*:\n\n{message}",
                            parse_mode='Markdown'
                        )
                        sent_count += 1
                    except Exception as e:
                        print(f"Error sending message to user {member.user_id}: {e}")

        await update.message.reply_text(f"✅ Сообщение отправлено {sent_count} участникам группы '{group_entity.name}'.")

    async def leave_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) != 1:
            await update.message.reply_text(
                "Использование: /leave_group <group_id>\n"
                "Например: /leave_group 123"
            )
            return

        try:
            group_id = int(args[0])
        except ValueError:
            await update.message.reply_text("ID группы должен быть числом.")
            return

        async with db.get_session() as session:
            stmt_membership = select(GroupMember).filter_by(
                group_id=group_id,
                user_id=update.effective_user.id
            )
            membership = await session.scalar(stmt_membership)

            if not membership:
                await update.message.reply_text("Вы не состоите в этой группе.")
                return

            group = await session.get(Group, group_id)
            if not group:
                await update.message.reply_text("Ошибка: Группа не найдена.")
                return

            if group.creator_id == update.effective_user.id:
                stmt_members = select(GroupMember).filter_by(group_id=group_id)
                members = await session.scalars(stmt_members)

                await session.delete(group)
                await session.commit()

                for member in members.all():
                    if member.user_id != update.effective_user.id:
                        try:
                            await context.bot.send_message(
                                chat_id=member.user_id,
                                text=f"Группа *'{group.name}'* была удалена ее создателем.",
                                parse_mode='Markdown'
                            )
                        except Exception:
                            pass

                await update.message.reply_text(
                    f"❌ Вы были создателем, поэтому группа '{group.name}' удалена для всех.")
            else:
                await session.delete(membership)
                await session.commit()

                await update.message.reply_text(f"👋 Вы успешно покинули группу '{group.name}'.")

                try:
                    await context.bot.send_message(
                        chat_id=group.creator_id,
                        text=f"Пользователь @{update.effective_user.username} покинул вашу группу *'{group.name}'*.",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

    async def group_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) != 1:
            await update.message.reply_text(
                "Использование: /group_info <group_id>\n"
                "Например: /group_info 123"
            )
            return

        try:
            group_id = int(args[0])
        except ValueError:
            await update.message.reply_text("ID группы должен быть числом.")
            return

        async with db.get_session() as session:
            stmt_membership = select(GroupMember).filter_by(
                group_id=group_id,
                user_id=update.effective_user.id
            )
            membership = await session.scalar(stmt_membership)

            if not membership:
                await update.message.reply_text("Вы не состоите в этой группе.")
                return

            group_entity = await session.get(Group, group_id)

            stmt_members = select(GroupMember).filter_by(
                group_id=group_id
            )
            members = await session.scalars(stmt_members)
            members = members.all()

            text = f"Информация о группе *'{group_entity.name}'* (ID: `{group_entity.id}`):\n\n"
            if group_entity.description:
                text += f"Описание: {group_entity.description}\n\n"

            text += f"Участников: {len(members)}\n"
            text += "Участники:\n"

            for member in members:
                stmt = select(User).filter_by(telegram_id=member.user_id)
                user = await session.scalar(stmt)
                if user:
                    role = "Админ" if member.is_admin else "Участник"
                    text += f"- {user.name} (@{user.username}) - {role}\n"

            await update.message.reply_text(text, parse_mode='Markdown')

    async def add_group_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) < 1:
            await update.message.reply_text(
                "Использование: /add_group_reminder <group_id>"
            )
            return ConversationHandler.END

        try:
            group_id = int(args[0])
            context.user_data['group'] = group_id

            async with db.get_session() as session:
                stmt_membership = select(GroupMember).filter_by(
                    group_id=group_id,
                    user_id=update.effective_user.id
                )
                membership = await session.scalar(stmt_membership)

                if not membership:
                    await update.message.reply_text("Вы не состоите в этой группе и не можете отправлять сообщения.")
                    return ConversationHandler.END

                group = await session.get(Group, group_id)
                if not group or not group.is_active:
                    await update.message.reply_text(f"Группа с ID {group_id} не найдена или неактивна.")
                    return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("ID группы должен быть числом.")
            return ConversationHandler.END

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
        return ADD_GROUP_REMINDER_TITLE

    async def add_group_reminder_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        title = update.message.text.strip()

        if len(title) < 1 or len(title) > 200:
            await update.message.reply_text("Название должно быть от 1 до 200 символов. Попробуйте еще раз:")
            return ADD_GROUP_REMINDER_TITLE

        context.user_data['title'] = title
        await update.message.reply_text("Введите описание (можно пропустить - skip):")
        return ADD_GROUP_REMINDER_DESCRIPTION

    async def add_group_reminder_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        description = update.message.text.strip()
        if description == "skip":
            description = ""

        description = f"Группа: `{context.user_data.get('group', 'Неизвестно')}`\n" + description

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
        return ADD_GROUP_REMINDER_TIME

    async def add_group_reminder_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        time_str = update.message.text.strip()
        user_id = update.effective_user.id

        async with db.get_session() as session:
            stmt = select(User).filter_by(telegram_id=user_id)
            user = await session.scalar(stmt)
            if not user:
                await update.message.reply_text("Ошибка: Пользователь не найден.")
                return ConversationHandler.END

            user_timezone = user.timezone

        try:
            reminder_dt_local = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
            user_tz = pytz.timezone(user_timezone)
            reminder_dt_local = user_tz.localize(reminder_dt_local)
            reminder_dt_utc_aware = reminder_dt_local.astimezone(pytz.utc)
        except ValueError:
            reminder_dt_utc_aware = self.date_parser.parse_natural_text(time_str, user_timezone)

        if not reminder_dt_utc_aware:
            await update.message.reply_text(
                "⚠️ Не удалось распознать дату и время.\n"
                "Пожалуйста, попробуйте написать проще (например, 'через 20 минут') или используйте формат ДД.ММ.ГГГГ ЧЧ:ММ."
            )
            return ADD_GROUP_REMINDER_TIME

        if reminder_dt_utc_aware < datetime.now(pytz.utc):
            await update.message.reply_text("Время напоминания не может быть в прошлом. Попробуйте еще раз:")
            return ADD_GROUP_REMINDER_TIME

        reminder_dt_utc_naive = reminder_dt_utc_aware.replace(tzinfo=None)

        user_display_tz = pytz.timezone(user_timezone)
        display_time = reminder_dt_utc_aware.astimezone(user_display_tz)

        group_id = context.user_data.get('group')

        sent_count = 0
        async with db.get_session() as session:
            stmt_members = select(GroupMember).filter_by(
                group_id=group_id
            )
            members = await session.scalars(stmt_members)
            members = members.all()

            for member in members:
                new_reminder = Reminder(
                    user_id=member.user_id,
                    title=context.user_data['title'],
                    description=context.user_data['description'],
                    reminder_time=reminder_dt_utc_naive,
                    timezone=user_timezone
                )
                session.add(new_reminder)
                sent_count += 1

            await session.commit()

        await update.message.reply_text(
            f"🎉 Напоминание '{new_reminder.title}' успешно добавлено для {sent_count} участников группы!\n"
            f"⏰ Сработает: {display_time.strftime('%d.%m.%Y %H:%M')} ({user_timezone})."
        )

        context.user_data.clear()
        return ConversationHandler.END