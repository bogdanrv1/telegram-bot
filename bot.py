import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, ConversationHandler, 
    MessageHandler, filters, CallbackQueryHandler
)
from telegram.constants import ParseMode
from database import User, Project, DailyTask, SessionLocal, create_tables, generate_project_id
from datetime import datetime, timedelta

# Настройка
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Админы (добавь свой Telegram ID)
ADMINS = [499188225, 6166088736]

# Состояния для диалогов
PROJECT_NAME, PROJECT_DAYS, DAILY_TASKS, REMINDER_TIME, START_DATE, PROJECT_OWNER, CONFIRM_PROJECT = range(7)
ADD_DAY, ADD_DAY_TASK, REMINDER_COUNT, REMINDER_TIMES, CHANGE_NAME, CONFIRM_NAME = range(7, 13)

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = get_db()
    
    # Регистрируем пользователя
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        # Получаем следующий short_id
        max_short_id = db.query(User.short_id).order_by(User.short_id.desc()).first()
        next_short_id = 1 if max_short_id is None else max_short_id[0] + 1
        
        db_user = User(id=user.id, username=user.username, short_id=next_short_id)
        db.add(db_user)
        db.commit()
    
    role = "👑 Админ" if is_admin(user.id) else "👤 Сотрудник"
    
    welcome_text = f"""
🎉 <b>Добро пожаловать в Project Manager Bot!</b>

👋 Привет, {user.username or user.id}!
🎯 Ваша роль: <b>{role}</b>

📋 <b>Доступные команды:</b>
• /newproject - Создать новый проект
• /myprojects - Мои проекты
• /projects - Все проекты (только админ)
• /users - Список пользователей (только админ)
• /help - Справка

🚀 <b>Начните с создания проекта:</b>
/newproject
"""
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 <b>Справка по командам:</b>

🎯 <b>Основные команды:</b>
• /newproject - Создать новый проект
• /myprojects - Показать мои проекты
• /complete [ID] - Завершить проект
• /plusoneday [ID] - Добавить день к проекту
• /daily [ID] - Показать задачи проекта
• /delete [ID] - Удалить проект
• /changename - Изменить свой никнейм

⚙️ <b>Настройки:</b>
• /remindersettings [ID] - Настройки напоминаний (количество и время)

👑 <b>Админские команды:</b>
• /projects - Все проекты в системе
• /users - Список пользователей
• /seereminder - Посмотреть пример сообщения напоминания

💡 <b>Примеры:</b>
• /newproject - создать проект
• /complete 0001 - завершить проект 0001
• /remindersettings 0001 - настроить напоминания для проекта 0001
• /daily 0001 - показать задачи проекта 0001
"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# Команда /users (только для админа)
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return
    
    db = get_db()
    users_list = db.query(User).all()
    
    lines = ["👥 <b>Пользователи системы:</b>"]
    for u in users_list:
        role = "👑 Админ" if is_admin(u.id) else "👤 Сотрудник"
        projects_count = len(u.projects)
        display_name = u.display_name or u.username or str(u.id)
        lines.append(f"<b>[{u.short_id}]</b> {display_name} — {role} 📊 {projects_count} проектов")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# Команда /projects (только для админа)
async def all_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return
    
    db = get_db()
    projects = db.query(Project).all()
    
    if not projects:
        await update.message.reply_text("📭 Проектов пока нет.")
        return
    
    lines = ["📋 <b>Все проекты в системе:</b>"]
    for p in projects:
        user = db.query(User).filter(User.id == p.user_id).first()
        status_emoji = {"active": "🟢", "completed": "✅", "paused": "⏸️"}
        status = status_emoji.get(p.status, "❓")
        user_name = user.display_name or user.username or str(user.id)
        lines.append(f"<b>[{p.project_id}]</b> {p.name} — {user_name} {status}")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# Команда /myprojects
async def my_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = get_db()
    
    projects = db.query(Project).filter(Project.user_id == user_id).all()
    
    if not projects:
        await update.message.reply_text(
            "📭 У вас пока нет проектов.\n\n🎯 Создайте первый проект командой:\n/newproject"
        )
        return
    
    # Разделяем проекты по статусу
    active_projects = [p for p in projects if p.status == "active"]
    completed_projects = [p for p in projects if p.status == "completed"]
    
    lines = [f"📋 <b>Мои проекты:</b>"]
    
    # Активные проекты
    if active_projects:
        lines.append("")
        lines.append("🟢 <b>Активные:</b>")
        for p in active_projects:
            completed_tasks = sum(1 for task in p.daily_tasks if task.completed == "completed")
            total_tasks = len(p.daily_tasks)
            progress = f"{completed_tasks}/{total_tasks}" if total_tasks > 0 else "0/0"
            
            # Вычисляем даты начала и окончания
            start_date = p.start_date
            end_date = start_date + timedelta(days=p.days_count - 1)
            
            # Получаем названия дней недели
            day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            start_day = day_names[start_date.weekday()]
            end_day = day_names[end_date.weekday()]
            
            lines.append(f"• <b>[{p.project_id}]</b> {p.name}")
            lines.append(f"  📅 {p.days_count} дней | ⏰ {p.reminder_time} | 📊 {progress}")
            lines.append(f"  📆 {start_date.strftime('%d.%m')}({start_day}) - {end_date.strftime('%d.%m')}({end_day})")
            lines.append("")
            if hasattr(p, 'created_by') and p.created_by and p.created_by != p.user_id:
                assigner = db.query(User).filter(User.id == p.created_by).first()
                assigner_name = assigner.display_name or assigner.username or str(assigner.id) if assigner else 'другой пользователь'
                lines.append(f"  👤 Назначил: {assigner_name}")
            print(f"[DEBUG] Проект {p.project_id}: created_by={getattr(p, 'created_by', None)}, user_id={p.user_id}")
    else:
        lines.append("")
        lines.append("🟢 <b>Активные:</b>")
        lines.append("📭 Нет активных проектов")
        lines.append("")
    
    # Завершенные проекты
    if completed_projects:
        lines.append("✅ <b>Завершенные:</b>")
        for p in completed_projects:
            completed_tasks = sum(1 for task in p.daily_tasks if task.completed == "completed")
            total_tasks = len(p.daily_tasks)
            progress = f"{completed_tasks}/{total_tasks}" if total_tasks > 0 else "0/0"
            
            # Вычисляем даты начала и окончания
            start_date = p.start_date
            end_date = start_date + timedelta(days=p.days_count - 1)
            
            # Получаем названия дней недели
            day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            start_day = day_names[start_date.weekday()]
            end_day = day_names[end_date.weekday()]
            
            lines.append(f"• <b>[{p.project_id}]</b> {p.name}")
            lines.append(f"  📅 {p.days_count} дней | ⏰ {p.reminder_time} | 📊 {progress}")
            lines.append(f"  📆 {start_date.strftime('%d.%m')}({start_day}) - {end_date.strftime('%d.%m')}({end_day})")
            lines.append("")
            if hasattr(p, 'created_by') and p.created_by and p.created_by != p.user_id:
                assigner = db.query(User).filter(User.id == p.created_by).first()
                assigner_name = assigner.display_name or assigner.username or str(assigner.id) if assigner else 'другой пользователь'
                lines.append(f"  👤 Назначил: {assigner_name}")
            print(f"[DEBUG] Проект {p.project_id}: created_by={getattr(p, 'created_by', None)}, user_id={p.user_id}")
    else:
        lines.append("✅ <b>Завершенные:</b>")
        lines.append("📭 Нет завершенных проектов")
        lines.append("")
    
    # Добавляем шаблон команд управления
    lines.append("📋 <b>Команды для управления проектами:</b>")
    lines.append("")
    lines.append("<b>ID проекта 0001(для примера):</b>")
    lines.append("• /complete 0001 - завершить проект")
    lines.append("• /plusoneday 0001 - добавить день")
    lines.append("• /daily 0001 - показать задачи")
    lines.append("• /delete 0001 - удалить проект")
    lines.append("• /remindersettings 0001 - настройки напоминаний")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# Создание нового проекта
async def newproject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 <b>Создание нового проекта</b>\n\n"
        "📝 Назовите ваш проект:",
        parse_mode=ParseMode.HTML
    )
    return PROJECT_NAME

async def newproject_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    project_name = update.message.text.strip()
    if len(project_name) > 100:
        await update.message.reply_text("❌ Название слишком длинное. Максимум 100 символов.")
        return PROJECT_NAME
    
    context.user_data['project'] = {'name': project_name}
    
    await update.message.reply_text(
        f"📝 <b>Проект:</b> {project_name}\n\n"
        "📅 Укажите количество дней для этого проекта (1-30):",
        parse_mode=ParseMode.HTML
    )
    return PROJECT_DAYS

async def newproject_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text)
        if days < 1 or days > 30:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите число от 1 до 30:")
        return PROJECT_DAYS
    
    context.user_data['project']['days_count'] = days
    context.user_data['project']['daily_tasks'] = []
    context.user_data['current_day'] = 1
    
    await update.message.reply_text(
        f"📅 <b>Количество дней:</b> {days}\n\n"
        "📝 Напишите, что вы будете делать в <b>День 1</b>:",
        parse_mode=ParseMode.HTML
    )
    return DAILY_TASKS

async def newproject_daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_description = update.message.text.strip()
    current_day = context.user_data['current_day']
    days_count = context.user_data['project']['days_count']
    
    context.user_data['project']['daily_tasks'].append({
        'day': current_day,
        'description': task_description
    })
    
    if current_day < days_count:
        context.user_data['current_day'] = current_day + 1
        await update.message.reply_text(
            f"✅ <b>День {current_day}</b> добавлен!\n\n"
            f"📝 Напишите, что вы будете делать в <b>День {current_day + 1}</b>:",
            parse_mode=ParseMode.HTML
        )
        return DAILY_TASKS
    else:
        await update.message.reply_text(
            f"✅ <b>День {current_day}</b> добавлен!\n\n"
            "⏰ Укажите время напоминания (HH:MM):\n"
            "Я буду каждый день напоминать вам о вашем проекте в одно и то же время",
            parse_mode=ParseMode.HTML
        )
        return REMINDER_TIME

async def newproject_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time = update.message.text.strip()
    import re
    if not re.match(r"^\d{2}:\d{2}$", time):
        await update.message.reply_text("❌ Введите время в формате HH:MM (например, 09:00):")
        return REMINDER_TIME
    
    context.user_data['project']['reminder_time'] = time
    
    await update.message.reply_text(
        f"⏰ <b>Время напоминания:</b> {time}\n\n"
        f"📅 Укажите дату начала проекта в формате ДД.ММ (например, 01.07):\n"
        f"Это будет первый день вашего проекта",
        parse_mode=ParseMode.HTML
    )
    return START_DATE

async def newproject_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    import re
    
    # Проверяем формат ДД.ММ
    if not re.match(r"^\d{2}\.\d{2}$", date_text):
        await update.message.reply_text("❌ Введите дату в формате ДД.ММ (например, 01.07):")
        return START_DATE
    
    try:
        day, month = date_text.split('.')
        day, month = int(day), int(month)
        
        # Проверяем валидность даты
        current_year = datetime.now().year
        start_date = datetime(current_year, month, day)
        
        # Проверяем, что дата не в прошлом
        if start_date < datetime.now():
            await update.message.reply_text("❌ Дата начала не может быть в прошлом. Введите другую дату:")
            return START_DATE
        
        # Проверяем, что дата не слишком далеко в будущем (максимум 1 год)
        max_future_date = datetime.now() + timedelta(days=365)
        if start_date > max_future_date:
            await update.message.reply_text("❌ Дата начала не может быть более чем через год. Введите другую дату:")
            return START_DATE
            
    except ValueError:
        await update.message.reply_text("❌ Неверная дата. Введите дату в формате ДД.ММ (например, 01.07):")
        return START_DATE
    
    context.user_data['project']['start_date'] = start_date
    
    # Показываем подтверждение
    project_data = context.user_data['project']
    lines = [
        f"📋 <b>Подтверждение проекта:</b>",
        f"",
        f"🎯 <b>Название:</b> {project_data['name']}",
        f"📅 <b>Дней:</b> {project_data['days_count']}",
        f"📆 <b>Дата начала:</b> {start_date.strftime('%d.%m.%Y')}",
        f"⏰ <b>Время напоминания:</b> {project_data['reminder_time']}",
        f"",
        f"📝 <b>Ежедневные задачи:</b>"
    ]
    
    for task in project_data['daily_tasks']:
        lines.append(f"<b>День {task['day']}:</b> {task['description']}")
    
    lines.append("")
    lines.append("👤 <b>Кому назначить проект?</b>")
    lines.append("")
    lines.append("• Напишите 'себе' для создания проекта для себя")
    lines.append("• Напишите Short ID пользователя (число в скобках)")
    lines.append("")
    
    # Получаем список пользователей
    db = get_db()
    users_list = db.query(User).all()
    if users_list:
        lines.append("👥 <b>Доступные пользователи:</b>")
        for user in users_list:
            display_name = user.display_name or user.username or str(user.id)
            role = "👑 Админ" if is_admin(user.id) else "👤 Сотрудник"
            lines.append(f"   • <b>[{user.short_id}]</b> {display_name} — {role}")
        lines.append("")
    
    lines.append("💡 <b>Подсказка:</b> Напишите число из скобок, например: 1, 2")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    return PROJECT_OWNER

async def newproject_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_input = update.message.text.strip().lower()
    db = get_db()
    
    if owner_input == "себе":
        # Проект для себя
        context.user_data['project']['owner_id'] = update.effective_user.id
        owner_name = "себя"
    else:
        # Проверяем, является ли ввод числом (ID пользователя)
        try:
            input_id = int(owner_input)
            
            # Сначала ищем по основному ID
            owner_user = db.query(User).filter(User.id == input_id).first()
            
            # Если не найден, ищем по short_id
            if not owner_user:
                owner_user = db.query(User).filter(User.short_id == input_id).first()
            
            if not owner_user:
                await update.message.reply_text(
                    f"❌ Пользователь с ID {input_id} не найден.\n\n"
                    f"💡 Используйте /users чтобы посмотреть список пользователей.\n"
                    f"   Можно использовать основной ID или Short ID.\n\n"
                    f"👤 Напишите 'себе' или ID пользователя:",
                    parse_mode=ParseMode.HTML
                )
                return PROJECT_OWNER
            
            context.user_data['project']['owner_id'] = owner_user.id  # Всегда используем основной ID
            owner_name = owner_user.display_name or owner_user.username or str(owner_user.id)
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Напишите 'себе' или ID пользователя (число):",
                parse_mode=ParseMode.HTML
            )
            return PROJECT_OWNER
    
    # Показываем финальное подтверждение
    project_data = context.user_data['project']
    start_date = project_data['start_date']
    
    lines = [
        f"📋 <b>Подтверждение проекта:</b>",
        f"",
        f"🎯 <b>Название:</b> {project_data['name']}",
        f"👤 <b>Владелец:</b> {owner_name}",
        f"📅 <b>Дней:</b> {project_data['days_count']}",
        f"📆 <b>Дата начала:</b> {start_date.strftime('%d.%m.%Y')}",
        f"⏰ <b>Время напоминания:</b> {project_data['reminder_time']}",
        f"",
        f"📝 <b>Ежедневные задачи:</b>"
    ]
    
    for task in project_data['daily_tasks']:
        lines.append(f"<b>День {task['day']}:</b> {task['description']}")
    
    lines.append("")
    lines.append("✅ Напишите 'да' для создания проекта или 'нет' для отмены:")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    return CONFIRM_PROJECT

async def newproject_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != 'да':
        await update.message.reply_text("❌ Создание проекта отменено.")
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    project_data = context.user_data['project']
    db = get_db()
    
    try:
        # Получаем ID владельца проекта
        owner_id = project_data.get('owner_id', user_id)  # По умолчанию создатель проекта
        print(f"[DEBUG] Создаём проект: name={project_data['name']}, owner_id={owner_id}, created_by={user_id}")
        # Создаем проект
        project = Project(
            project_id=generate_project_id(),
            user_id=owner_id,  # Используем указанного владельца
            name=project_data['name'],
            days_count=project_data['days_count'],
            reminder_time=project_data['reminder_time'],
            start_date=project_data.get('start_date', datetime.now() + timedelta(days=1)),
            created_by=user_id  # Сохраняем, кто назначил
        )
        db.add(project)
        db.commit()  # Сначала сохраняем проект
        print(f"[DEBUG] Проект сохранён: id={project.id}, project_id={project.project_id}, created_by={project.created_by}, user_id={project.user_id}")
        
        # Создаем ежедневные задачи
        for task_data in project_data['daily_tasks']:
            daily_task = DailyTask(
                project_id=project.id,
                day_number=task_data['day'],
                description=task_data['description']
            )
            db.add(daily_task)
        
        db.commit()  # Сохраняем задачи
        
        # Формируем сообщение об успехе
        
        # Получаем дату начала проекта
        start_date = project.start_date
        day_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        day_name = day_names[start_date.weekday()]
        
        # Получаем информацию о владельце проекта
        owner_user = db.query(User).filter(User.id == owner_id).first()
        owner_name = owner_user.display_name or owner_user.username or str(owner_user.id)
        
        # Определяем, кто создал проект
        creator_user = db.query(User).filter(User.id == user_id).first()
        creator_name = creator_user.display_name or creator_user.username or str(creator_user.id)
        
        success_text = f"""
🎉 <b>Проект успешно создан!</b>

📋 <b>Детали проекта:</b>
• <b>Название:</b> {project.name}
• <b>ID проекта:</b> <code>{project.project_id}</code>
• <b>Владелец:</b> {owner_name}
• <b>Создал:</b> {creator_name}
• <b>Дней:</b> {project.days_count}
• <b>Время напоминания:</b> {project.reminder_time}

🚀 <b>Проект стартует {start_date.strftime('%d.%m')}({day_name}) в {project.reminder_time}</b>

📋 <b>Доступные команды:</b>
• /complete {project.project_id} - завершить проект
• /plusoneday {project.project_id} - добавить день
• /daily {project.project_id} - показать задачи
• /delete {project.project_id} - удалить проект
• /remindersettings {project.project_id} - настройки напоминаний
• /myprojects - мои проекты
"""
        
        await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)
        
        # Уведомление назначенному пользователю
        if owner_id != user_id:
            try:
                print(f"[DEBUG] Пробую отправить уведомление пользователю {owner_id}")
                notify_text = (
                    f"👋 <b>Привет!</b>\n\n"
                    f"Пользователь <b>{creator_name}</b> назначил вам новый проект!\n\n"
                    f"• <b>Название:</b> {project.name}\n"
                    f"• <b>ID:</b> <code>{project.project_id}</code>\n\n"
                    f"Посмотреть все проекты: /myprojects"
                )
                await context.bot.send_message(chat_id=owner_id, text=notify_text, parse_mode=ParseMode.HTML)
                print(f"[DEBUG] Уведомление отправлено пользователю {owner_id}")
            except Exception as e:
                print(f"[DEBUG] Не удалось отправить уведомление: {e}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка создания проекта: {e}")
        logger.error(f"Детали проекта: {project_data}")
        await update.message.reply_text(f"❌ Ошибка при создании проекта: {str(e)}")
    
    return ConversationHandler.END

async def newproject_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Создание проекта отменено.")
    return ConversationHandler.END

# Команда /complete [ID]
async def complete_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используйте: /complete [ID проекта]")
        return
    
    project_id = context.args[0]
    user_id = update.effective_user.id
    db = get_db()
    
    project = db.query(Project).filter(
        Project.project_id == project_id,
        Project.user_id == user_id
    ).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден или у вас нет к нему доступа.")
        return
    
    if project.status == "completed":
        await update.message.reply_text("✅ Проект уже завершен.")
        return
    
    project.status = "completed"
    db.commit()
    
    await update.message.reply_text(
        f"🎉 <b>Проект завершен!</b>\n\n"
        f"📋 <b>{project.name}</b> (ID: {project.project_id})\n"
        f"✅ Статус: Завершен",
        parse_mode=ParseMode.HTML
    )

# Команда /plusoneday [ID]
async def add_day_to_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используйте: /plusoneday [ID проекта]")
        return ConversationHandler.END
    
    project_id = context.args[0]
    user_id = update.effective_user.id
    db = get_db()
    
    project = db.query(Project).filter(
        Project.project_id == project_id,
        Project.user_id == user_id
    ).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден или у вас нет к нему доступа.")
        return ConversationHandler.END
    
    if project.status == "completed":
        await update.message.reply_text("❌ Нельзя добавить день к завершенному проекту.")
        return ConversationHandler.END
    
    # Увеличиваем количество дней
    project.days_count += 1
    db.commit()
    
    # Сохраняем данные проекта в контексте
    context.user_data['add_day'] = {
        'project_id': project.project_id,
        'project_name': project.name,
        'new_day': project.days_count
    }
    
    await update.message.reply_text(
        f"📅 <b>Добавление дня к проекту</b>\n\n"
        f"📋 Проект: {project.name} (ID: {project.project_id})\n"
        f"📅 Новый день: {project.days_count}\n\n"
        f"📝 Напишите, что вы будете делать в <b>День {project.days_count}</b>:",
        parse_mode=ParseMode.HTML
    )
    return ADD_DAY_TASK

# Обработка ввода задачи для нового дня
async def add_day_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_description = update.message.text.strip()
    add_day_data = context.user_data['add_day']
    
    db = get_db()
    
    # Находим проект
    project = db.query(Project).filter(Project.project_id == add_day_data['project_id']).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден.")
        return ConversationHandler.END
    
    # Создаем новую ежедневную задачу
    new_day_task = DailyTask(
        project_id=project.id,
        day_number=add_day_data['new_day'],
        description=task_description
    )
    db.add(new_day_task)
    db.commit()
    
    await update.message.reply_text(
        f"✅ <b>День успешно добавлен!</b>\n\n"
        f"📋 Проект: {project.name} (ID: {project.project_id})\n"
        f"📅 День {add_day_data['new_day']}: {task_description}\n"
        f"📊 Всего дней: {project.days_count}",
        parse_mode=ParseMode.HTML
    )
    
    # Очищаем данные
    context.user_data.pop('add_day', None)
    
    return ConversationHandler.END

# Команда /daily [ID]
async def show_daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используйте: /daily [ID проекта]")
        return
    
    project_id = context.args[0]
    user_id = update.effective_user.id
    db = get_db()
    
    project = db.query(Project).filter(
        Project.project_id == project_id,
        Project.user_id == user_id
    ).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден или у вас нет к нему доступа.")
        return
    
    # Получаем все задачи проекта
    tasks = db.query(DailyTask).filter(DailyTask.project_id == project.id).order_by(DailyTask.day_number).all()
    
    if not tasks:
        await update.message.reply_text("❌ У проекта нет задач.")
        return
    
    lines = [f"📅 <b>Задачи проекта {project.name} (ID: {project.project_id}):</b>"]
    
    for task in tasks:
        status_emoji = {"pending": "⏳", "completed": "✅", "skipped": "⏭️"}
        status = status_emoji.get(task.completed, "❓")
        lines.append(f"<b>День {task.day_number}:</b> {task.description} {status}")
    
    lines.append("")
    lines.append("💡 <b>Статусы:</b>")
    lines.append("⏳ - ожидает выполнения")
    lines.append("✅ - выполнено")
    lines.append("⏭️ - пропущено")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# Команда /delete [ID]
async def delete_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используйте: /delete [ID проекта]")
        return
    
    project_id = context.args[0]
    user_id = update.effective_user.id
    db = get_db()
    
    project = db.query(Project).filter(
        Project.project_id == project_id,
        Project.user_id == user_id
    ).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден или у вас нет к нему доступа.")
        return
    
    project_name = project.name
    
    # Удаляем проект (каскадно удалятся и задачи)
    db.delete(project)
    db.commit()
    
    await update.message.reply_text(
        f"🗑️ <b>Проект удален!</b>\n\n"
        f"📋 <b>{project_name}</b> (ID: {project_id})\n"
        f"✅ Проект и все его задачи удалены",
        parse_mode=ParseMode.HTML
    )

# Команда /remindersettings [ID]
async def reminder_settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используйте: /remindersettings [ID проекта]")
        return ConversationHandler.END
    
    project_id = context.args[0]
    user_id = update.effective_user.id
    db = get_db()
    
    project = db.query(Project).filter(
        Project.project_id == project_id,
        Project.user_id == user_id
    ).first()
    
    if not project:
        await update.message.reply_text("❌ Проект не найден или у вас нет к нему доступа.")
        return ConversationHandler.END
    
    context.user_data['reminder_settings'] = {'project_id': project_id}
    
    await update.message.reply_text(
        f"⏰ <b>Настройки напоминаний</b>\n\n"
        f"📋 Проект: {project.name} (ID: {project_id})\n"
        f"🕐 Текущее время: {project.reminder_time}\n\n"
        f"Сколько раз в день вам напоминать? (1-5):",
        parse_mode=ParseMode.HTML
    )
    return REMINDER_COUNT

async def reminder_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        if count < 1 or count > 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите число от 1 до 5:")
        return REMINDER_COUNT
    
    context.user_data['reminder_settings']['count'] = count
    
    await update.message.reply_text(
        f"✅ Количество напоминаний: {count}\n\n"
        f"Теперь напишите время напоминаний (пример: 12:00 14:00 16:00):",
        parse_mode=ParseMode.HTML
    )
    return REMINDER_TIMES

async def reminder_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    times_text = update.message.text.strip()
    count = context.user_data['reminder_settings']['count']
    
    # Парсим времена
    import re
    times = re.findall(r'\d{2}:\d{2}', times_text)
    
    if len(times) != count:
        await update.message.reply_text(f"❌ Нужно указать ровно {count} времени. Попробуйте еще раз:")
        return REMINDER_TIMES
    
    # Проверяем формат времени
    for time in times:
        if not re.match(r'^\d{2}:\d{2}$', time):
            await update.message.reply_text("❌ Неверный формат времени. Используйте HH:MM:")
            return REMINDER_TIMES
    
    project_id = context.user_data['reminder_settings']['project_id']
    db = get_db()
    
    project = db.query(Project).filter(Project.project_id == project_id).first()
    
    # Сохраняем настройки (пока просто обновляем время на первое)
    project.reminder_time = times[0]  # Пока сохраняем только первое время
    db.commit()
    
    times_str = " ".join(times)
    
    await update.message.reply_text(
        f"✅ <b>Настройки напоминаний обновлены!</b>\n\n"
        f"📋 Проект: {project.name} (ID: {project_id})\n"
        f"⏰ Время напоминаний: {times_str}\n"
        f"📅 Теперь я буду напоминать вам {count} раз в день о работе над проектом",
        parse_mode=ParseMode.HTML
    )
    
    # Очищаем данные
    context.user_data.pop('reminder_settings', None)
    
    return ConversationHandler.END

# Команда /seereminder (только для админа)
async def see_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return
    
    # Показываем пример сообщения напоминания
    reminder_text = f"""
🔔 <b>Напоминание о проекте</b>

📋 <b>Проект:</b> Пример проекта
🆔 <b>ID:</b> 0001
📅 <b>День:</b> 1 из 3
⏰ <b>Время:</b> 12:00

📝 <b>Задача на сегодня:</b>
Смотреть

💡 <b>Статус:</b> ⏳ Ожидает выполнения

🎯 <b>Прогресс:</b> 0/3 задач выполнено

✅ <b>Команды для управления:</b>
• /complete_task 0001 1 - выполнить задачу
• /skip_task 0001 1 - пропустить задачу
• /daily 0001 - посмотреть все задачи
"""
    
    await update.message.reply_text(reminder_text, parse_mode=ParseMode.HTML)

# Команда /changename
async def change_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = get_db()
    
    logger.info(f"Попытка изменения никнейма для пользователя {user_id}")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"Пользователь {user_id} не найден в базе данных")
        await update.message.reply_text(
            "❌ Пользователь не найден в базе данных.\n\n"
            "💡 Попробуйте сначала использовать команду /start для регистрации.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    current_name = user.display_name or user.username or str(user.id)
    logger.info(f"Текущий никнейм пользователя {user_id}: {current_name}")
    
    await update.message.reply_text(
        f"👤 <b>Изменение никнейма</b>\n\n"
        f"🔄 Текущий никнейм: <b>{current_name}</b>\n\n"
        f"📝 Введите новый никнейм:",
        parse_mode=ParseMode.HTML
    )
    return CHANGE_NAME

async def change_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    
    if len(new_name) > 100:
        await update.message.reply_text("❌ Никнейм слишком длинный. Максимум 100 символов.")
        return CHANGE_NAME
    
    if len(new_name) < 2:
        await update.message.reply_text("❌ Никнейм слишком короткий. Минимум 2 символа.")
        return CHANGE_NAME
    
    context.user_data['new_name'] = new_name
    
    await update.message.reply_text(
        f"📝 <b>Подтверждение изменения никнейма</b>\n\n"
        f"🔄 Текущий: <b>{update.effective_user.username or update.effective_user.id}</b>\n"
        f"✨ Новый: <b>{new_name}</b>\n\n"
        f"✅ Напишите 'да' для подтверждения или 'нет' для отмены:",
        parse_mode=ParseMode.HTML
    )
    return CONFIRM_NAME

async def change_name_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != 'да':
        await update.message.reply_text("❌ Изменение никнейма отменено.")
        return ConversationHandler.END
    
    new_name = context.user_data['new_name']
    user_id = update.effective_user.id
    db = get_db()
    
    logger.info(f"Подтверждение изменения никнейма для пользователя {user_id} на '{new_name}'")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"Пользователь {user_id} не найден при подтверждении")
        await update.message.reply_text("❌ Пользователь не найден.")
        return ConversationHandler.END
    
    old_name = user.display_name or user.username or str(user.id)
    user.display_name = new_name
    
    try:
        db.commit()
        logger.info(f"Никнейм успешно изменен: {old_name} → {new_name}")
        
        await update.message.reply_text(
            f"✅ <b>Никнейм успешно изменен!</b>\n\n"
            f"🔄 <b>{old_name}</b> → <b>{new_name}</b>\n\n"
            f"👤 Теперь вы отображаетесь как <b>{new_name}</b>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении никнейма: {e}")
        db.rollback()
        await update.message.reply_text("❌ Ошибка при сохранении никнейма. Попробуйте еще раз.")
    
    # Очищаем данные
    context.user_data.pop('new_name', None)
    
    return ConversationHandler.END

# Основная функция
def main():
    logger.info("Запуск Project Manager Bot...")
    
    # Создаем таблицы
    create_tables()
    
    # Получаем токен
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN не найден!")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("projects", all_projects))
    application.add_handler(CommandHandler("seereminder", see_reminder))
    application.add_handler(CommandHandler("myprojects", my_projects))
    application.add_handler(CommandHandler("complete", complete_project))
    application.add_handler(CommandHandler("daily", show_daily_tasks))
    application.add_handler(CommandHandler("delete", delete_project))
    
    # Диалог создания проекта
    newproject_handler = ConversationHandler(
        entry_points=[CommandHandler("newproject", newproject_start)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_name)],
            PROJECT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_days)],
            DAILY_TASKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_daily_tasks)],
            REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_reminder_time)],
            START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_start_date)],
            PROJECT_OWNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_owner)],
            CONFIRM_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, newproject_confirm)],
        },
        fallbacks=[CommandHandler("cancel", newproject_cancel)],
    )
    application.add_handler(newproject_handler)
    
    # Диалог добавления дня
    add_day_handler = ConversationHandler(
        entry_points=[CommandHandler("plusoneday", add_day_to_project)],
        states={
            ADD_DAY_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_day_task)],
        },
        fallbacks=[CommandHandler("cancel", newproject_cancel)],
    )
    application.add_handler(add_day_handler)
    
    # Диалог настроек напоминаний
    reminder_settings_handler = ConversationHandler(
        entry_points=[CommandHandler("remindersettings", reminder_settings_start)],
        states={
            REMINDER_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_count)],
            REMINDER_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_times)],
        },
        fallbacks=[CommandHandler("cancel", newproject_cancel)],
    )
    application.add_handler(reminder_settings_handler)
    
    # Диалог изменения никнейма
    change_name_handler = ConversationHandler(
        entry_points=[CommandHandler("changename", change_name_start)],
        states={
            CHANGE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_name_input)],
            CONFIRM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_name_confirm)],
        },
        fallbacks=[CommandHandler("cancel", newproject_cancel)],
    )
    application.add_handler(change_name_handler)
    
    logger.info("Project Manager Bot запущен!")
    application.run_polling()

if __name__ == "__main__":
    main() 
