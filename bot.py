import json
import logging
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session, joinedload
from contextlib import contextmanager

# Импортируем наши модели и функции для работы с БД
from database import SessionLocal, User, Project, create_db_and_tables

# Загружаем переменные окружения из файла .env
load_dotenv('.env')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CHOOSING_TYPE, CHOOSING_EMPLOYEE, TASK_NAME, TASK_DAYS, TASK_DAY_CONTENT, REMINDER_TIME = range(6)

# Админы (руководители) - замените на реальные ID
ADMINS = [499188225]

@contextmanager
def get_db_session():
    """Контекстный менеджер для работы с сессиями БД."""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    return user_id in ADMINS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню. Теперь работает с БД."""
    logger.info(f"Команда /start вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    with get_db_session() as db:
        # Ищем пользователя в БД или создаем нового
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Создан новый пользователь: {username} ({user_id})")

        if is_admin(user_id):
            # Меню для руководителей
            all_projects = db.query(Project).filter(Project.leader_id == user_id).all()
            all_active = [p for p in all_projects if p.status == 'active']
            all_completed = [p for p in all_projects if p.status == 'completed']
            employee_count = db.query(User).count()

            message = f"👋 Привет! Ты руководитель команды.\n\n"
            message += f"📊 Статистика:\n"
            message += f"• Активных проектов: {len(all_active)}\n"
            message += f"• Сотрудников: {employee_count}\n"
            message += f"• Завершенных задач: {len(all_completed)}\n\n"
            
            if all_active:
                message += "📋 Твои проекты:\n"
                # Используем joinedload для эффективной загрузки связанных данных
                projects_to_show = db.query(Project).options(joinedload(Project.assignee)).filter(Project.leader_id == user_id, Project.status == 'active').limit(5).all()
                for project in projects_to_show:
                    status_emoji = "🟢"
                    assignee_username = project.assignee.username if project.assignee else 'Неизвестно'
                    message += f"{status_emoji} ID: {project.id} - {project.project_name} (Исполнитель: @{assignee_username})\n"
        else:
            # Меню для сотрудников
            active_projects = db.query(Project).filter(Project.assignee_id == user_id, Project.status == 'active').all()
            completed_projects = db.query(Project).filter(Project.assignee_id == user_id, Project.status == 'completed').all()
            
            message = f"👋 Привет! Ты исполнитель.\n\n"
            message += f"📊 Твоя статистика:\n"
            message += f"• Активных задач: {len(active_projects)}\n"
            message += f"• Завершенных: {len(completed_projects)}\n"
            message += f"• Время уведомлений: {user.reminder_time}\n\n"
            
            if active_projects:
                message += "📋 Твои задачи:\n"
                for project in active_projects[:3]:
                    day_index = (date.today() - project.start_date).days
                    total_days = len(project.daily_plan)
                    status_emoji = "🟢" if day_index < total_days else "🟡"
                    message += f"{status_emoji} ID: {project.id} - {project.project_name} (День {day_index + 1} из {total_days})\n"

    # Общая часть сообщения с командами
    if is_admin(user_id):
        message += "\nДоступные команды:\n"
        message += "/create_task - создать новую задачу\n"
        message += "/team_status - статус команды\n"
        message += "/employee_list - список сотрудников\n"
        message += "/edit_project ID - редактировать проект\n"
        message += "/edit_task ID - просмотр задачи\n"
        message += "/pause_task ID - приостановить\n"
        message += "/resume_task ID - возобновить\n"
        message += "/finish_task ID - завершить\n"
        message += "/reopen_task ID - открыть заново\n"
        message += "/clear_history - очистить историю\n"
        message += "/edit_task_name ID название - изменить название\n"
        message += "/edit_task_plan ID день план - изменить план\n"
        message += "/set_reminder_time время - время уведомлений\n"
        message += "/toggle_reminder - вкл/выкл уведомления\n"
    else:
        message += "\nДоступные команды:\n"
        message += "/my_tasks - мои задачи\n"
        message += "/create_task - создать свою задачу\n"
        message += "/edit_task ID - просмотр задачи\n"
        message += "/pause_task ID - приостановить\n"
        message += "/resume_task ID - возобновить\n"
        message += "/finish_task ID - завершить\n"
        message += "/reopen_task ID - открыть заново\n"
        message += "/clear_history - очистить историю\n"
        message += "/edit_task_name ID название - изменить название\n"
        message += "/edit_task_plan ID день план - изменить план\n"
        message += "/set_reminder_time время - время уведомлений\n"
        message += "/toggle_reminder - вкл/выкл уведомления\n"
        message += "/help - справка по командам\n"

    await update.message.reply_text(message)

async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания задачи. Без изменений в логике, только в реализации."""
    logger.info(f"Команда /create_task вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("1️⃣ Назначить сотруднику", callback_data="create_for_employee")],
            [InlineKeyboardButton("2️⃣ Создать для себя", callback_data="create_for_self")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Кто будет выполнять?", reply_markup=reply_markup)
        return CHOOSING_TYPE
    else:
        context.user_data['create_type'] = 'self'
        await update.message.reply_text("Введите название задачи:")
        return TASK_NAME

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопок. Теперь загружает сотрудников из БД."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "create_for_employee":
        context.user_data['create_type'] = 'employee'
        with get_db_session() as db:
            # Ищем всех пользователей, кто не является админом
            employees = db.query(User).filter(User.id.notin_(ADMINS)).all()
            
            if not employees:
                await query.edit_message_text("Нет доступных сотрудников.")
                context.user_data.clear()
                return ConversationHandler.END

            message_lines = ["Выберите сотрудника:"]
            for emp in employees:
                # Подсчитываем активные задачи для каждого
                active_tasks = db.query(Project).filter(Project.assignee_id == emp.id, Project.status == 'active').count()
                message_lines.append(f"👤 @{emp.username} (ID: {emp.id}) - {active_tasks} активных задач")
            
            message_lines.append("\nВведите ID сотрудника:")
            await query.edit_message_text("\n".join(message_lines))
        return CHOOSING_EMPLOYEE
        
    elif query.data == "create_for_self":
        context.user_data['create_type'] = 'self'
        await query.edit_message_text("Введите название задачи:")
        return TASK_NAME
    
    return CHOOSING_TYPE

async def handle_employee_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора сотрудника по ID. Проверяет наличие в БД."""
    try:
        employee_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Попробуйте еще раз.")
        return CHOOSING_EMPLOYEE

    with get_db_session() as db:
        employee = db.query(User).filter(User.id == employee_id).first()
        
        if employee and not is_admin(employee.id):
            context.user_data['selected_employee_id'] = employee.id
            await update.message.reply_text(f"✅ Выбран сотрудник: @{employee.username}\n\nВведите название задачи:")
            return TASK_NAME
        else:
            await update.message.reply_text("❌ Сотрудник не найден или является руководителем. Введите корректный ID.")
            return CHOOSING_EMPLOYEE

async def handle_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['task_name'] = update.message.text.strip()
    await update.message.reply_text("Сколько дней потребуется для выполнения? (число)")
    return TASK_DAYS

async def handle_task_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        days = int(update.message.text.strip())
        if not (1 <= days <= 30):
            raise ValueError()
        context.user_data['task_days'] = days
        context.user_data['daily_plan'] = []
        context.user_data['current_day'] = 1
        await update.message.reply_text("День 1: Что нужно сделать?")
        return TASK_DAY_CONTENT
    except ValueError:
        await update.message.reply_text("Введите число от 1 до 30.")
        return TASK_DAYS

async def handle_day_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    day_content = update.message.text.strip()
    context.user_data['daily_plan'].append(day_content)
    current_day = context.user_data['current_day']
    total_days = context.user_data['task_days']
    
    if current_day < total_days:
        context.user_data['current_day'] += 1
        await update.message.reply_text(f"День {current_day + 1}: Что нужно сделать?")
        return TASK_DAY_CONTENT
    else:
        # Убрал запрос времени, так как оно уже есть у пользователя.
        # Можно добавить команду для его изменения.
        return await save_task_and_finish(update, context)

async def save_task_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет задачу в БД и завершает диалог."""
    user_id = update.effective_user.id
    
    with get_db_session() as db:
        # Определяем исполнителя
        if context.user_data.get('create_type') == 'employee':
            assignee_id = context.user_data.get('selected_employee_id')
        else:
            assignee_id = user_id

        assignee_user = db.query(User).filter(User.id == assignee_id).first()
        if not assignee_user:
             # Этого не должно случиться, но на всякий случай
            await update.message.reply_text("Ошибка: исполнитель не найден.")
            return ConversationHandler.END

        # Создаем новый проект
        new_project = Project(
            project_name=context.user_data['task_name'],
            leader_id=user_id,
            assignee_id=assignee_id,
            start_date=date.today(),
            status='active',
            daily_plan=context.user_data['daily_plan']
        )
        db.add(new_project)
        db.commit()

        message = f"✅ Задача \"{new_project.project_name}\" создана!\n"
        message += f"👤 Исполнитель: @{assignee_user.username}\n"
        message += f"📅 Дней: {len(new_project.daily_plan)}\n"
        
        await update.message.reply_text(message)
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Создание задачи отменено.")
    return ConversationHandler.END

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает задачи пользователя, получая их из БД."""
    user_id = update.effective_user.id
    with get_db_session() as db:
        # Логика для админа и сотрудника
        if is_admin(user_id):
            projects = db.query(Project).options(joinedload(Project.assignee)).filter(Project.leader_id == user_id).all()
            role_text = "проекты"
        else:
            projects = db.query(Project).filter(Project.assignee_id == user_id).all()
            role_text = "задачи"
        
        if not projects:
            await update.message.reply_text(f"У тебя пока нет {role_text}.")
            return
        
        message = f"📋 Твои {role_text}:\n\n"
        for p in projects:
            # ... (логика форматирования вывода, как и раньше, но с объектами SQLAlchemy)
            message += f"ID: {p.id} - {p.project_name} (Статус: {p.status})\n"
        await update.message.reply_text(message)

async def team_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус команды"""
    logger.info(f"Команда /team_status вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("Эта команда доступна только руководителям.")
        return
    
    projects_data, _ = load_data()
    user_projects = [p for p in projects_data['projects'] if p['leader_id'] == user_id]
    
    active_projects = [p for p in user_projects if p['status'] == 'active']
    completed_projects = [p for p in user_projects if p['status'] == 'completed']
    paused_projects = [p for p in user_projects if p['status'] == 'paused']
    
    # Статистика по сотрудникам
    employee_stats = {}
    for project in user_projects:
        assignee_id = project['assignee_id']
        if assignee_id not in employee_stats:
            employee_stats[assignee_id] = {'active': 0, 'completed': 0, 'paused': 0}
        employee_stats[assignee_id][project['status']] += 1
    
    message = "📊 Статус команды:\n\n"
    message += f"📈 Общая статистика:\n"
    message += f"• Активных проектов: {len(active_projects)}\n"
    message += f"• Завершенных: {len(completed_projects)}\n"
    message += f"• Приостановленных: {len(paused_projects)}\n"
    message += f"• Всего проектов: {len(user_projects)}\n\n"
    
    if employee_stats:
        message += "👥 По сотрудникам:\n"
        for assignee_id, stats in employee_stats.items():
            username = projects_data['users'].get(assignee_id, {}).get('username', 'Неизвестно')
            message += f"• @{username}: {stats['active']} активных, {stats['completed']} завершенных\n"
    
    if active_projects:
        message += "\n🟢 Активные проекты:\n"
        for project in active_projects[:5]:  # Показываем первые 5
            assignee = projects_data['users'].get(project['assignee_id'], {}).get('username', 'Неизвестно')
            start_date = datetime.strptime(project['start_date'], '%Y-%m-%d').date()
            day_index = (date.today() - start_date).days
            total_days = len(project['daily_plan'])
            message += f"• ID: {project['project_id']} - {project['project_name']} (@{assignee}, день {day_index + 1}/{total_days})\n"
    
    await update.message.reply_text(message)

async def employee_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список сотрудников"""
    logger.info(f"Команда /employee_list вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("Эта команда доступна только руководителям.")
        return
    
    projects_data, _ = load_data()
    
    message = "👥 Список сотрудников:\n\n"
    
    for user_id, user_info in projects_data['users'].items():
        if not is_admin(user_id):
            # Подсчитываем задачи сотрудника
            user_projects = [p for p in projects_data['projects'] if p['assignee_id'] == user_id]
            active_tasks = len([p for p in user_projects if p['status'] == 'active'])
            completed_tasks = len([p for p in user_projects if p['status'] == 'completed'])
            
            reminder_time = user_info.get('reminder_time', '09:00')
            reminder_enabled = user_info.get('reminder_enabled', True)
            
            status_emoji = "🟢" if active_tasks > 0 else "⚪"
            reminder_emoji = "🔔" if reminder_enabled else "🔕"
            
            message += f"{status_emoji} @{user_info['username']}\n"
            message += f"   📊 Задач: {active_tasks} активных, {completed_tasks} завершенных\n"
            message += f"   {reminder_emoji} Уведомления: {reminder_time}\n\n"
    
    message += "Команды:\n"
    message += "/create_task - создать задачу для сотрудника\n"
    message += "/team_status - общий статус команды\n"
    
    await update.message.reply_text(message)

async def edit_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование проекта (перенаправляет на edit_task)"""
    logger.info(f"Команда /edit_project вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    # Проверяем, передан ли ID проекта
    if not context.args:
        await update.message.reply_text("Использование: /edit_project ID\nПример: /edit_project 1")
        return
    
    # Перенаправляем на универсальную функцию edit_task
    await edit_task(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    logger.info(f"Команда /help вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if is_admin(user_id):
        message = "📚 Справка по командам\n\n"
        message += "👨‍💼 Для руководителей:\n"
        message += "/create_task - создать задачу\n"
        message += "/my_tasks - все проекты\n"
        message += "/team_status - статус команды\n"
        message += "/employee_list - список сотрудников\n"
        message += "/edit_project ID - редактировать проект\n\n"
        message += "🔧 Управление задачами:\n"
        message += "/edit_task ID - просмотр задачи\n"
        message += "/pause_task ID - приостановить\n"
        message += "/resume_task ID - возобновить\n"
        message += "/finish_task ID - завершить\n"
        message += "/reopen_task ID - открыть заново\n"
        message += "/clear_history - очистить историю\n\n"
        message += "📝 Редактирование:\n"
        message += "/edit_task_name ID название - изменить название\n"
        message += "/edit_task_plan ID день план - изменить план\n\n"
        message += "⏰ Уведомления:\n"
        message += "/set_reminder_time время - время уведомлений\n"
        message += "/toggle_reminder - вкл/выкл уведомления\n\n"
    else:
        message = "📚 Справка по командам\n\n"
        message += "👤 Для сотрудников:\n"
        message += "/my_tasks - мои задачи\n"
        message += "/create_task - создать свою задачу\n"
        message += "/edit_task ID - просмотр задачи\n\n"
        message += "🔧 Управление задачами:\n"
        message += "/pause_task ID - приостановить\n"
        message += "/resume_task ID - возобновить\n"
        message += "/finish_task ID - завершить\n"
        message += "/reopen_task ID - открыть заново\n"
        message += "/clear_history - очистить историю\n\n"
        message += "📝 Редактирование:\n"
        message += "/edit_task_name ID название - изменить название\n"
        message += "/edit_task_plan ID день план - изменить план\n\n"
        message += "⏰ Уведомления:\n"
        message += "/set_reminder_time время - время уведомлений\n"
        message += "/toggle_reminder - вкл/выкл уведомления\n\n"
        message += "ℹ️ Справка:\n"
        message += "/help - эта справка\n\n"
    
    message += "🆘 Поддержка: @admin"
    
    await update.message.reply_text(message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
    
    # Отправляем сообщение пользователю об ошибке
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка при обработке команды. Попробуйте еще раз или обратитесь к администратору."
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений, не являющихся командами."""
    # Эта функция может быть использована для ответов на общие вопросы или
    # когда бот не находится в каком-либо диалоге.
    logger.info(f"Получено текстовое сообщение от {update.effective_user.id}: '{update.message.text}'")
    # await update.message.reply_text("Я получил ваше сообщение, но не знаю, как на него ответить. Используйте /help для списка команд.")

async def edit_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование/просмотр задачи. Загружает данные из БД."""
    logger.info(f"Команда /edit_task вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    
    try:
        task_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /edit_task ID\nПример: /edit_task 1")
        return

    with get_db_session() as db:
        # Ищем задачу и сразу подгружаем связанные данные (leader, assignee)
        # чтобы избежать дополнительных запросов к БД.
        task = db.query(Project).options(
            joinedload(Project.leader),
            joinedload(Project.assignee)
        ).filter(Project.id == task_id).first()

        if not task:
            await update.message.reply_text(f"Задача с ID {task_id} не найдена.")
            return

        # Проверка прав доступа
        if user_id != task.leader_id and user_id != task.assignee_id:
            await update.message.reply_text("У вас нет прав на просмотр этой задачи.")
            return
            
        leader_username = task.leader.username if task.leader else "Неизвестно"
        assignee_username = task.assignee.username if task.assignee else "Неизвестно"
        day_index = (date.today() - task.start_date).days
        total_days = len(task.daily_plan)

        message = f"📝 Задача ID: {task.id}\n\n"
        message += f"📋 Название: {task.project_name}\n"
        message += f"👤 Исполнитель: @{assignee_username}\n"
        message += f"👨‍💼 Руководитель: @{leader_username}\n"
        message += f"📊 Статус: {task.status}\n"
        message += f"📅 День {day_index + 1} из {total_days}\n"

        # План на сегодня
        if task.status == 'active' and 0 <= day_index < total_days:
            today_plan = task.daily_plan[day_index]
            message += f"🟢 План на сегодня (День {day_index + 1}):\n{today_plan}\n\n"
        
        # Общий план
        message += "📋 Общий план:\n"
        for i, task_content in enumerate(task.daily_plan, 1):
            if i <= day_index and task.status == 'completed':
                status_icon = "✅"
            elif i <= day_index and task.status != 'completed':
                 status_icon = "✔️" # День прошел, но задача не завершена
            elif i == day_index + 1 and task.status == 'active':
                status_icon = "🟢"
            else:
                status_icon = "⏳"
            message += f"{status_icon} День {i}: {task_content}\n"
        
        # Доступные действия
        message += "\n🔧 Доступные действия:\n"
        if task.status == 'active':
            message += f"• /pause_task {task.id} - приостановить\n"
            message += f"• /finish_task {task.id} - завершить\n"
        elif task.status == 'paused':
            message += f"• /resume_task {task.id} - возобновить\n"
        elif task.status == 'completed':
            message += f"• /reopen_task {task.id} - открыть заново\n"

        await update.message.reply_text(message)

async def pause_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приостановка задачи"""
    logger.info(f"Команда /pause_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text("Использование: /pause_task ID\nПример: /pause_task 1")
        return
    
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /pause_task 1")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    if task['status'] != 'active':
        await update.message.reply_text("Можно приостановить только активные задачи.")
        return
    
    # Приостанавливаем задачу
    task['status'] = 'paused'
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Задача \"{task['project_name']}\" приостановлена.")

async def resume_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возобновление задачи"""
    logger.info(f"Команда /resume_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text("Использование: /resume_task ID\nПример: /resume_task 1")
        return
    
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /resume_task 1")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    if task['status'] != 'paused':
        await update.message.reply_text("Можно возобновить только приостановленные задачи.")
        return
    
    # Возобновляем задачу
    task['status'] = 'active'
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Задача \"{task['project_name']}\" возобновлена.")

async def finish_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение задачи"""
    logger.info(f"Команда /finish_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text("Использование: /finish_task ID\nПример: /finish_task 1")
        return
    
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /finish_task 1")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    if task['status'] == 'completed':
        await update.message.reply_text("Задача уже завершена.")
        return
    
    # Завершаем задачу
    task['status'] = 'completed'
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Задача \"{task['project_name']}\" завершена!")

async def reopen_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открытие завершенной задачи заново"""
    logger.info(f"Команда /reopen_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text("Использование: /reopen_task ID\nПример: /reopen_task 1")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /reopen_task 1")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    if task['status'] != 'completed':
        await update.message.reply_text("Можно открыть заново только завершенные задачи.")
        return
    
    # Открываем задачу заново
    task['status'] = 'active'
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Задача \"{task['project_name']}\" открыта заново.")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка истории завершенных задач"""
    logger.info(f"Команда /clear_history вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    projects_data, tasks_data = load_data()
    
    # Подсчитываем завершенные задачи
    if is_admin(user_id):
        # Админы могут очищать только свои завершенные задачи
        completed_tasks = [p for p in projects_data['projects'] if p['status'] == 'completed' and p['leader_id'] == user_id]
    else:
        # Сотрудники могут очищать только свои завершенные задачи
        completed_tasks = [p for p in projects_data['projects'] if p['status'] == 'completed' and p['assignee_id'] == user_id]
    
    if not completed_tasks:
        await update.message.reply_text("У тебя нет завершенных задач для очистки.")
        return
    
    # Удаляем завершенные задачи
    if is_admin(user_id):
        projects_data['projects'] = [p for p in projects_data['projects'] if not (p['status'] == 'completed' and p['leader_id'] == user_id)]
    else:
        projects_data['projects'] = [p for p in projects_data['projects'] if not (p['status'] == 'completed' and p['assignee_id'] == user_id)]
    
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"🗑️ Очищено {len(completed_tasks)} завершенных задач из истории.")

async def edit_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменение названия задачи"""
    logger.info(f"Команда /edit_task_name вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /edit_task_name ID новое_название\nПример: /edit_task_name 1 Новая задача")
        return
    
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /edit_task_name 1 Новая задача")
        return
    
    new_name = ' '.join(context.args[1:])
    if not new_name.strip():
        await update.message.reply_text("Название не может быть пустым.")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    # Изменяем название
    old_name = task['project_name']
    task['project_name'] = new_name
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Название задачи изменено:\n\"{old_name}\" → \"{new_name}\"")

async def edit_task_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменение плана задачи"""
    logger.info(f"Команда /edit_task_plan вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("Использование: /edit_task_plan ID день новый_план\nПример: /edit_task_plan 1 2 Новый план на день 2")
        return
    
    try:
        task_id = int(context.args[0])
        day_number = int(context.args[1])
    except ValueError:
        await update.message.reply_text("ID задачи и номер дня должны быть числами. Пример: /edit_task_plan 1 2 Новый план")
        return
    
    new_plan = ' '.join(context.args[2:])
    if not new_plan.strip():
        await update.message.reply_text("План не может быть пустым.")
        return
    
    projects_data, tasks_data = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
            break
    
    if not task:
        await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    # Проверяем номер дня
    if day_number < 1 or day_number > len(task['daily_plan']):
        await update.message.reply_text(f"Номер дня должен быть от 1 до {len(task['daily_plan'])}.")
        return
    
    # Изменяем план
    old_plan = task['daily_plan'][day_number - 1]
    task['daily_plan'][day_number - 1] = new_plan
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ План дня {day_number} изменен:\n\"{old_plan}\" → \"{new_plan}\"")

async def set_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка времени уведомлений"""
    logger.info(f"Команда /set_reminder_time вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if not context.args:
        await update.message.reply_text("Использование: /set_reminder_time время\nПример: /set_reminder_time 09:00")
        return
    
    time_str = context.args[0]
    
    # Проверяем формат времени
    try:
        from datetime import datetime
        datetime.strptime(time_str, '%H:%M')
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Используйте формат ЧЧ:ММ\nПример: /set_reminder_time 09:00")
        return
    
    projects_data, tasks_data = load_data()
    
    # Обновляем время уведомлений пользователя
    if user_id not in projects_data['users']:
        await update.message.reply_text("Сначала зарегистрируйтесь с помощью /start")
        return
    
    projects_data['users'][user_id]['reminder_time'] = time_str
    save_data(projects_data, tasks_data)
    
    await update.message.reply_text(f"✅ Время уведомлений установлено: {time_str}")

async def toggle_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение/выключение уведомлений"""
    logger.info(f"Команда /toggle_reminder вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    projects_data, tasks_data = load_data()
    
    if user_id not in projects_data['users']:
        await update.message.reply_text("Сначала зарегистрируйтесь с помощью /start")
        return
    
    current_status = projects_data['users'][user_id].get('reminder_enabled', True)
    new_status = not current_status
    
    projects_data['users'][user_id]['reminder_enabled'] = new_status
    save_data(projects_data, tasks_data)
    
    status_text = "включены" if new_status else "выключены"
    emoji = "🔔" if new_status else "🔕"
    
    await update.message.reply_text(f"{emoji} Уведомления {status_text}")

async def send_daily_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправка ежедневных напоминаний о задачах"""
    logger.info("Запуск отправки ежедневных напоминаний")
    
    projects_data, tasks_data = load_data()
    current_time = datetime.now().strftime('%H:%M')
    today = date.today()
    
    for user_id, user_info in projects_data['users'].items():
        # Проверяем, включены ли уведомления у пользователя
        if not user_info.get('reminder_enabled', True):
            continue
        
        # Проверяем время уведомлений
        reminder_time = user_info.get('reminder_time', '09:00')
        if current_time != reminder_time:
            continue
        
        # Получаем активные задачи пользователя
        user_tasks = []
        for project in projects_data['projects']:
            if project['assignee_id'] == user_id and project['status'] == 'active':
                start_date = datetime.strptime(project['start_date'], '%Y-%m-%d').date()
                day_index = (today - start_date).days
                total_days = len(project['daily_plan'])
                
                if day_index >= 0 and day_index < total_days:
                    user_tasks.append({
                        'project': project,
                        'day_index': day_index,
                        'total_days': total_days,
                        'today_plan': project['daily_plan'][day_index]
                    })
        
        if not user_tasks:
            continue
        
        # Формируем сообщение
        message = f"👋 Привет! Вот что у тебя запланировано на сегодня:\n\n"
        
        for task_info in user_tasks:
            project = task_info['project']
            day_index = task_info['day_index']
            total_days = task_info['total_days']
            today_plan = task_info['today_plan']
            
            message += f"📋 **{project['project_name']}** (День {day_index + 1} из {total_days})\n"
            message += f"📝 План на сегодня: {today_plan}\n\n"
        
        message += "💡 Не забудь отметить прогресс в задачах!"
        
        try:
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
            logger.info(f"Отправлено напоминание пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")

def main():
    """Запуск бота"""
    # ПРИМЕЧАНИЕ: Создаем таблицы в БД перед запуском бота.
    # Эта функция безопасна для повторного запуска, она не будет создавать таблицы, если они уже есть.
    logger.info("Проверка и создание таблиц в базе данных...")
    create_db_and_tables()
    logger.info("Таблицы готовы.")

    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("Ошибка: Не найден TELEGRAM_TOKEN")
        return
    
    application = Application.builder().token(token).build()
    
    # Добавляем планировщик для ежедневных напоминаний
    job_queue = application.job_queue
    job_queue.run_repeating(send_daily_reminders, interval=60, first=10)  # Каждую минуту, первая проверка через 10 секунд
    logger.info("Планировщик ежедневных напоминаний добавлен")
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Сначала добавляем все обычные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("my_tasks", my_tasks))
    application.add_handler(CommandHandler("team_status", team_status))
    application.add_handler(CommandHandler("employee_list", employee_list))
    application.add_handler(CommandHandler("edit_project", edit_project))
    application.add_handler(CommandHandler("help", help_command))
    
    # Добавляем команды для редактирования задач
    application.add_handler(CommandHandler("edit_task", edit_task))
    application.add_handler(CommandHandler("pause_task", pause_task))
    application.add_handler(CommandHandler("resume_task", resume_task))
    application.add_handler(CommandHandler("finish_task", finish_task))
    application.add_handler(CommandHandler("reopen_task", reopen_task))
    application.add_handler(CommandHandler("clear_history", clear_history))
    
    # Добавляем команды для редактирования содержимого задач
    application.add_handler(CommandHandler("edit_task_name", edit_task_name))
    application.add_handler(CommandHandler("edit_task_plan", edit_task_plan))
    
    # Добавляем команды для управления уведомлениями
    application.add_handler(CommandHandler("set_reminder_time", set_reminder_time))
    application.add_handler(CommandHandler("toggle_reminder", toggle_reminder))
    
    # Добавляем ConversationHandler для создания задачи
    logger.info("Создаем ConversationHandler для create_task")
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create_task', create_task)],
        states={
            CHOOSING_TYPE: [CallbackQueryHandler(button_handler, pattern='^create_for_employee$|^create_for_self$')],
            CHOOSING_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_employee_choice)],
            TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_name)],
            TASK_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_days)],
            TASK_DAY_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day_content)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="create_task_conversation",
        persistent=False,
        allow_reentry=True
    )
    application.add_handler(conv_handler)
    logger.info("ConversationHandler добавлен")
    
    # Добавляем обработчик для всех остальных текстовых сообщений (должен идти после ConversationHandler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
