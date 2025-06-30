import json
import logging
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv('.env')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Изменено на DEBUG для более подробного логирования
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CHOOSING_TYPE, CHOOSING_EMPLOYEE, TASK_NAME, TASK_DAYS, TASK_DAY_CONTENT, REMINDER_TIME = range(6)

# Файлы для хранения данных
PROJECTS_FILE = 'projects.json'
TASKS_FILE = 'tasks.json'

# Админы (руководители) - замените на реальные ID
ADMINS = ['499188225']  # Добавьте сюда ID руководителей

def load_data():
    """Загрузка данных из файлов"""
    try:
        with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
            projects_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        projects_data = {"projects": [], "users": {}, "next_project_id": 1}
    
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            tasks_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tasks_data = {}
    
    return projects_data, tasks_data

def save_data(projects_data, tasks_data):
    """Сохранение данных в файлы"""
    with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(projects_data, f, ensure_ascii=False, indent=2)
    
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks_data, f, ensure_ascii=False, indent=2)

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return str(user_id) in ADMINS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    logger.info(f"Команда /start вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    
    projects_data, tasks_data = load_data()
    
    # Добавляем пользователя в базу, если его нет
    if user_id not in projects_data['users']:
        projects_data['users'][user_id] = {
            'username': username,
            'reminder_time': '09:00',
            'reminder_enabled': True
        }
        save_data(projects_data, tasks_data)
    
    # Получаем проекты пользователя
    user_projects = [p for p in projects_data['projects'] if p['assignee_id'] == user_id]
    active_projects = [p for p in user_projects if p['status'] == 'active']
    completed_projects = [p for p in user_projects if p['status'] == 'completed']
    
    if is_admin(user_id):
        # Меню для руководителей
        all_projects = [p for p in projects_data['projects'] if p['leader_id'] == user_id]
        all_active = [p for p in all_projects if p['status'] == 'active']
        all_completed = [p for p in all_projects if p['status'] == 'completed']
        
        message = f"👋 Привет! Ты руководитель команды.\n\n"
        message += f"📊 Статистика:\n"
        message += f"• Активных проектов: {len(all_active)}\n"
        message += f"• Сотрудников: {len(projects_data['users'])}\n"
        message += f"• Завершенных задач: {len(all_completed)}\n\n"
        
        if all_active:
            message += "📋 Твои проекты:\n"
            for project in all_active[:5]:  # Показываем первые 5
                status_emoji = "🟢" if project['status'] == 'active' else "🟡"
                assignee = projects_data['users'].get(project['assignee_id'], {}).get('username', 'Неизвестно')
                message += f"{status_emoji} ID: {project['project_id']} - {project['project_name']} (Исполнитель: @{assignee})\n"
        
        message += "\nДоступные команды:\n"
        message += "/create_task - создать новую задачу\n"
        message += "/my_tasks - все мои проекты\n"
        message += "/team_status - статус команды\n"
        message += "/employee_list - список сотрудников\n"
        message += "/edit_project ID - редактировать проект\n"
        
    else:
        # Меню для сотрудников
        user_info = projects_data['users'][user_id]
        reminder_time = user_info.get('reminder_time', '09:00')
        
        message = f"👋 Привет! Ты исполнитель.\n\n"
        message += f"📊 Твоя статистика:\n"
        message += f"• Активных задач: {len(active_projects)}\n"
        message += f"• Завершенных: {len(completed_projects)}\n"
        message += f"• Время уведомлений: {reminder_time}\n\n"
        
        if active_projects:
            message += "📋 Твои задачи:\n"
            for project in active_projects[:3]:  # Показываем первые 3
                start_date = datetime.strptime(project['start_date'], '%Y-%m-%d').date()
                day_index = (date.today() - start_date).days
                total_days = len(project['daily_plan'])
                status_emoji = "🟢" if day_index < total_days else "🟡"
                message += f"{status_emoji} ID: {project['project_id']} - {project['project_name']} (День {day_index + 1} из {total_days})\n"
        
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

async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания задачи"""
    logger.info(f"Команда /create_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    if is_admin(user_id):
        # Для руководителей - выбор типа создания
        keyboard = [
            [InlineKeyboardButton("1️⃣ Назначить сотруднику", callback_data="create_for_employee")],
            [InlineKeyboardButton("2️⃣ Создать для себя", callback_data="create_for_self")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "Создание новой задачи\n\nКто будет выполнять?\n1️⃣ Назначить сотруднику\n2️⃣ Создать для себя\n\nВыберите вариант:"
        await update.message.reply_text(message, reply_markup=reply_markup)
        return CHOOSING_TYPE
    else:
        # Для сотрудников - сразу создаем для себя
        context.user_data['create_type'] = 'self'
        await update.message.reply_text("Введите название задачи:\nПример: Дизайн лендинга для интернет-магазина")
        return TASK_NAME

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"Обработка callback_query: {query.data}")
    
    if query.data == "create_for_employee":
        context.user_data['create_type'] = 'employee'
        context.user_data['conversation_state'] = CHOOSING_EMPLOYEE
        logger.info(f"Установлен тип создания: employee для пользователя {query.from_user.id}")
        projects_data, _ = load_data()
        
        # Показываем список сотрудников
        employees = []
        for user_id, user_info in projects_data['users'].items():
            if not is_admin(user_id) and user_info.get('username'):  # Проверяем, что username не None
                active_tasks = len([p for p in projects_data['projects'] if p['assignee_id'] == user_id and p['status'] == 'active'])
                employees.append(f"👤 @{user_info['username']} (ID: {user_id}) - {active_tasks} активных задач")
        
        if not employees:
            await query.edit_message_text("Нет доступных сотрудников. Создайте задачу для себя.")
            context.user_data['create_type'] = 'self'
            context.user_data['conversation_state'] = TASK_NAME
            await query.message.reply_text("Введите название задачи:\nПример: Дизайн лендинга для интернет-магазина")
            return TASK_NAME
        
        message = "Выберите сотрудника:\n\n" + "\n".join(employees) + "\n\nВведите ID сотрудника (например: 6166088736):"
        logger.info(f"Отправляем список сотрудников: {employees}")
        await query.edit_message_text(message)
        logger.info(f"Возвращаем состояние CHOOSING_EMPLOYEE для пользователя {query.from_user.id}")
        return CHOOSING_EMPLOYEE
        
    elif query.data == "create_for_self":
        context.user_data['create_type'] = 'self'
        context.user_data['conversation_state'] = TASK_NAME
        await query.edit_message_text("Введите название задачи:\nПример: Дизайн лендинга для интернет-магазина")
        return TASK_NAME

async def handle_employee_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора сотрудника"""
    logger.info(f"handle_employee_choice вызвана для пользователя {update.effective_user.id}")
    logger.info(f"Введенный текст: '{update.message.text}'")
    logger.info(f"Текущее состояние: {context.user_data.get('conversation_state', 'не установлено')}")
    
    employee_input = update.message.text.strip()
    projects_data, _ = load_data()
    
    # Ищем сотрудника по ID (приоритет) или username
    selected_employee_id = None
    selected_employee_name = None
    
    # Сначала проверяем по ID
    if employee_input in projects_data['users']:
        user_info = projects_data['users'][employee_input]
        if not is_admin(employee_input) and user_info.get('username'):
            selected_employee_id = employee_input
            selected_employee_name = user_info['username']
            logger.info(f"Сотрудник найден по ID: {selected_employee_id} (@{selected_employee_name})")
    
    # Если не найден по ID, ищем по username
    if not selected_employee_id:
        for user_id, user_info in projects_data['users'].items():
            if not is_admin(user_id) and user_info.get('username') == employee_input:
                selected_employee_id = user_id
                selected_employee_name = user_info['username']
                logger.info(f"Сотрудник найден по username: {selected_employee_id} (@{selected_employee_name})")
                break
            
    if selected_employee_id:
        context.user_data['selected_employee_id'] = selected_employee_id
        context.user_data['conversation_state'] = TASK_NAME
        logger.info(f"Сотрудник выбран: {selected_employee_id} (@{selected_employee_name})")
        await update.message.reply_text(f"✅ Выбран сотрудник: @{selected_employee_name} (ID: {selected_employee_id})\n\nВведите название задачи:\nПример: Дизайн лендинга для интернет-магазина")
        return TASK_NAME
    else:
        # Показываем список доступных сотрудников для справки
        available_employees = []
        for user_id, user_info in projects_data['users'].items():
            if not is_admin(user_id) and user_info.get('username'):
                available_employees.append(f"👤 @{user_info['username']} (ID: {user_id})")
        
        error_message = "❌ Сотрудник не найден.\n\n"
        error_message += "Доступные сотрудники:\n" + "\n".join(available_employees) + "\n\n"
        error_message += "Введите ID сотрудника (например: 6166088736) или введите /cancel для отмены."
        logger.info(f"Сотрудник не найден. Доступные: {available_employees}")
        await update.message.reply_text(error_message)
        return CHOOSING_EMPLOYEE

async def handle_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"handle_task_name вызвана для пользователя {update.effective_user.id}")
    logger.info(f"Введенный текст: '{update.message.text}'")
    task_name = update.message.text.strip()
    context.user_data['task_name'] = task_name
    context.user_data['conversation_state'] = TASK_DAYS
    logger.info(f"Установлено название задачи: {task_name}")
    await update.message.reply_text("Сколько дней потребуется для выполнения?\nВведите число дней (например: 5)")
    return ConversationHandler.END

async def handle_task_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"handle_task_days вызвана для пользователя {update.effective_user.id}")
    logger.info(f"Введенный текст: '{update.message.text}'")
    try:
        days = int(update.message.text.strip())
        if days <= 0 or days > 30:
            await update.message.reply_text("Количество дней должно быть от 1 до 30. Попробуйте еще раз:")
            return ConversationHandler.END
        context.user_data['task_days'] = days
        context.user_data['daily_plan'] = []
        context.user_data['current_day'] = 1
        context.user_data['conversation_state'] = TASK_DAY_CONTENT
        logger.info(f"Установлено количество дней: {days}")
        await update.message.reply_text("День 1: Что нужно сделать?\nВведите задачу для 1-го дня:\n\nПример: Создание мокапов главной страницы")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введите корректное число дней (например: 5)")
        return ConversationHandler.END

async def handle_day_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day_content = update.message.text.strip()
    context.user_data['daily_plan'].append(day_content)
    current_day = context.user_data['current_day']
    total_days = context.user_data['task_days']
    if current_day < total_days:
        context.user_data['current_day'] = current_day + 1
        context.user_data['conversation_state'] = TASK_DAY_CONTENT
        await update.message.reply_text(f"День {current_day + 1}: Что нужно сделать?\nВведите задачу для {current_day + 1}-го дня:\n\nПример: Создание мокапов главной страницы")
        return ConversationHandler.END
    else:
        context.user_data['conversation_state'] = REMINDER_TIME
        await update.message.reply_text("В какое время отправлять уведомления?\nВведите время в формате ЧЧ:ММ\n\nПример: 09:00")
        return ConversationHandler.END

async def handle_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        datetime.strptime(time_str, '%H:%M')
        context.user_data['reminder_time'] = time_str
        context.user_data['conversation_state'] = None
        projects_data, tasks_data = load_data()
        user_id = str(update.effective_user.id)
        new_project = {
            'project_id': projects_data['next_project_id'],
            'project_name': context.user_data['task_name'],
            'leader_id': user_id,
            'assignee_id': context.user_data.get('selected_employee_id', user_id),
            'assignee_username': projects_data['users'].get(context.user_data.get('selected_employee_id', user_id), {}).get('username', ''),
            'start_date': date.today().isoformat(),
            'status': 'active',
            'daily_plan': context.user_data['daily_plan'],
            'time_per_task': 3,
            'active_tasks': {}
        }
        projects_data['projects'].append(new_project)
        projects_data['next_project_id'] += 1
        assignee_id = context.user_data.get('selected_employee_id', user_id)
        if assignee_id in projects_data['users']:
            projects_data['users'][assignee_id]['reminder_time'] = time_str
        save_data(projects_data, tasks_data)
        assignee_name = projects_data['users'].get(assignee_id, {}).get('username', 'Вы')
        message = f"✅ Задача создана!\n\n"
        message += f"📋 \"{context.user_data['task_name']}\"\n"
        message += f"👤 Исполнитель: @{assignee_name}\n"
        message += f"📅 Дней: {context.user_data['task_days']}\n"
        message += f"⏰ Уведомления: {time_str}\n\n"
        message += "📋 План:\n"
        for i, task in enumerate(context.user_data['daily_plan'], 1):
            message += f"День {i}: {task}\n"
        message += f"\nКоманды:\n"
        message += f"/my_tasks - посмотреть все задачи\n"
        context.user_data.clear()
        await update.message.reply_text(message)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Используйте формат ЧЧ:ММ (например: 09:00)")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания задачи"""
    context.user_data.clear()
    await update.message.reply_text("❌ Создание задачи отменено.")
    return ConversationHandler.END

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать задачи/проекты пользователя"""
    logger.info(f"Команда /my_tasks вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    projects_data, _ = load_data()
    
    if is_admin(user_id):
        # Для руководителей - показываем проекты, где они руководители
        user_projects = [p for p in projects_data['projects'] if p['leader_id'] == user_id]
        role_text = "проекты"
    else:
        # Для сотрудников - показываем задачи, где они исполнители
        user_projects = [p for p in projects_data['projects'] if p['assignee_id'] == user_id]
        role_text = "задачи"
    
    if not user_projects:
        await update.message.reply_text(f"У тебя пока нет {role_text}.")
        return

    message = f"📋 Твои {role_text}:\n\n"
    
    for project in user_projects:
        start_date = datetime.strptime(project['start_date'], '%Y-%m-%d').date()
        day_index = (date.today() - start_date).days
        total_days = len(project['daily_plan'])
        if day_index < total_days:
            current_task = project['daily_plan'][day_index]
        else:
            current_task = "Проект завершен"
        # Определяем статус
        if project['status'] == 'completed':
            status_emoji = "✅"
            status_text = "Завершено"
        elif project['status'] == 'paused':
            status_emoji = "⏸️"
            status_text = "Приостановлено"
        else:
            status_emoji = "🟢"
            status_text = "В работе" if day_index < total_days else "Не начато"
        message += f"{status_emoji} ID: {project['project_id']} - \"{project['project_name']}\"\n"
        if is_admin(user_id):
            assignee = projects_data['users'].get(project['assignee_id'], {}).get('username', 'Неизвестно')
            message += f"👤 Исполнитель: @{assignee}\n"
        else:
            message += f"📝 Задача: {current_task}\n"
            message += f"⏰ Уведомления: {projects_data['users'][user_id].get('reminder_time', '09:00')}\n"
        message += f"📅 День {day_index + 1} из {total_days}\n"
        if project['status'] == 'active' and day_index >= 0:
            if day_index < total_days:
                progress_percent = int((day_index + 1) / total_days * 100)
                message += f"📈 Прогресс: {progress_percent}% ({day_index + 1}/{total_days})\n"
            else:
                message += f"📈 Прогресс: 100% (срок превышен на {day_index - total_days + 1} дней)\n"
        elif project['status'] == 'completed':
            message += f"📈 Прогресс: 100% (завершено)\n"
        elif project['status'] == 'paused':
            if day_index >= 0 and day_index < total_days:
                progress_percent = int((day_index + 1) / total_days * 100)
                message += f"📈 Прогресс: {progress_percent}% (приостановлено)\n"
            else:
                message += f"📈 Прогресс: 100% (приостановлено)\n"
        message += f"📊 Статус: {status_text}\n\n"
    
    # Показываем доступные команды в зависимости от роли
    if is_admin(user_id):
        message += "Доступные команды:\n"
        message += "/create_task - создать новую задачу\n"
        message += "/team_status - статус команды\n"
        message += "/employee_list - список сотрудников\n"
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
        message += "Доступные команды:\n"
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
    """Обработчик всех текстовых сообщений"""
    user_id = str(update.effective_user.id)
    conversation_state = context.user_data.get('conversation_state')
    
    logger.info(f"handle_text_message вызвана для пользователя {user_id}")
    logger.info(f"Состояние беседы: {conversation_state}")
    logger.info(f"Текст сообщения: '{update.message.text}'")
    
    if conversation_state == CHOOSING_EMPLOYEE:
        return await handle_employee_choice(update, context)
    elif conversation_state == TASK_NAME:
        return await handle_task_name(update, context)
    elif conversation_state == TASK_DAYS:
        return await handle_task_days(update, context)
    elif conversation_state == TASK_DAY_CONTENT:
        return await handle_day_content(update, context)
    elif conversation_state == REMINDER_TIME:
        return await handle_reminder_time(update, context)
    else:
        # Если нет активного состояния, игнорируем сообщение
        logger.info(f"Нет активного состояния для пользователя {user_id}")
        return ConversationHandler.END

async def edit_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование задачи"""
    logger.info(f"Команда /edit_task вызвана пользователем {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    
    # Проверяем, передан ли ID задачи
    if not context.args:
        await update.message.reply_text("Использование: /edit_task ID\nПример: /edit_task 1")
        return
    
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пример: /edit_task 1")
        return
    
    projects_data, _ = load_data()
    
    # Ищем задачу
    task = None
    if is_admin(user_id):
        # Админы могут редактировать задачи, где они руководители
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['leader_id'] == user_id:
                task = p
                break
    else:
        # Сотрудники могут редактировать задачи, где они исполнители
        for p in projects_data['projects']:
            if p['project_id'] == task_id and p['assignee_id'] == user_id:
                task = p
                break
    
    if not task:
        if is_admin(user_id):
            await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        else:
            await update.message.reply_text(f"Задача с ID {task_id} не найдена или у тебя нет прав на её редактирование.")
        return
    
    # Показываем информацию о задаче
    assignee = projects_data['users'].get(task['assignee_id'], {}).get('username', 'Неизвестно')
    leader = projects_data['users'].get(task['leader_id'], {}).get('username', 'Неизвестно')
    start_date = datetime.strptime(task['start_date'], '%Y-%m-%d').date()
    day_index = (date.today() - start_date).days
    total_days = len(task['daily_plan'])
    
    message = f"📝 Редактирование задачи ID: {task_id}\n\n"
    message += f"📋 Название: {task['project_name']}\n"
    message += f"👤 Исполнитель: @{assignee}\n"
    message += f"👨‍💼 Руководитель: @{leader}\n"
    message += f"📊 Статус: {task['status']}\n"
    message += f"📅 День {day_index + 1} из {total_days}\n"
    
    # Добавляем информацию о прогрессе
    if task['status'] == 'active' and day_index >= 0:
        if day_index < total_days:
            progress_percent = int((day_index + 1) / total_days * 100)
            message += f"📈 Прогресс: {progress_percent}% ({day_index + 1}/{total_days})\n"
        else:
            message += f"📈 Прогресс: 100% (срок превышен на {day_index - total_days + 1} дней)\n"
    elif task['status'] == 'completed':
        message += f"📈 Прогресс: 100% (завершено)\n"
    elif task['status'] == 'paused':
        if day_index >= 0 and day_index < total_days:
            progress_percent = int((day_index + 1) / total_days * 100)
            message += f"📈 Прогресс: {progress_percent}% (приостановлено)\n"
        else:
            message += f"📈 Прогресс: 100% (приостановлено)\n"
    
    # Показываем план на сегодня, если задача активна и не превышен срок
    if task['status'] == 'active' and day_index >= 0 and day_index < total_days:
        today_plan = task['daily_plan'][day_index]
        message += f"🟢 План на сегодня (День {day_index + 1}):\n{today_plan}\n\n"
    elif task['status'] == 'active' and day_index >= total_days:
        message += f"🟡 Задача превысила срок на {day_index - total_days + 1} дней\n\n"
    elif task['status'] == 'paused':
        message += f"⏸️ Задача приостановлена\n\n"
    elif task['status'] == 'completed':
        message += f"✅ Задача завершена\n\n"
    
    message += "📋 Общий план:\n"
    for i, task_content in enumerate(task['daily_plan'], 1):
        if i <= day_index:
            status_icon = "✅"
        elif i == day_index + 1 and task['status'] == 'active':
            status_icon = "🟢"
        else:
            status_icon = "⏳"
        message += f"{status_icon} День {i}: {task_content}\n"
    
    # Показываем доступные действия
    message += "\n🔧 Доступные действия:\n"
    if task['status'] == 'active':
        message += "• /pause_task ID - приостановить задачу\n"
        message += "• /finish_task ID - завершить задачу\n"
    elif task['status'] == 'paused':
        message += "• /resume_task ID - возобновить задачу\n"
        message += "• /finish_task ID - завершить задачу\n"
    elif task['status'] == 'completed':
        message += "• /reopen_task ID - открыть задачу заново\n"
    
    message += "• /edit_task_name ID название - изменить название\n"
    message += "• /edit_task_plan ID день план - изменить план дня\n"
    
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
    # Получаем токен из переменных окружения
    token = os.getenv('TELEGRAM_TOKEN')
    logger.info(f"Токен из переменных окружения: {token[:10]}..." if token else "Токен не найден")
    
    if not token:
        logger.error("Ошибка: Не найден TELEGRAM_TOKEN в переменных окружения")
        print("Проверьте файл .env и убедитесь, что он содержит строку: TELEGRAM_TOKEN=ваш_токен")
        return
    
    # Создаем приложение
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
    
    # Добавляем обработчик для callback_query
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Добавляем обработчик для всех текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Затем добавляем ConversationHandler (должен быть последним)
    logger.info("Создаем ConversationHandler для create_task")
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create_task', create_task)],
        states={
            CHOOSING_TYPE: [CallbackQueryHandler(button_handler)],
            CHOOSING_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)],
            TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)],
            TASK_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)],
            TASK_DAY_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)],
            REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="create_task_conversation",
        persistent=False,
        allow_reentry=True
    )
    application.add_handler(conv_handler)
    logger.info("ConversationHandler добавлен")
    
    # Запускаем бота
    logger.info("Бот запущен...")
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()