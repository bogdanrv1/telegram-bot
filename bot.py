import logging
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# Импортируем наши модели и функции для работы с БД
from database import Project, SessionLocal, User, create_db_and_tables

# --- Настройка ---
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога ---
TASK_NAME, TASK_DAYS, TASK_DAY_CONTENT = range(3)

# --- Работа с базой данных ---
@contextmanager
def get_db_session():
    """Контекстный менеджер для безопасной работы с сессиями БД."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Команды бота ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает /start. Регистрирует нового пользователя."""
    user = update.effective_user
    logger.info(f"Команда /start от пользователя {user.username} ({user.id})")

    with get_db_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()
        if not db_user:
            db_user = User(id=user.id, username=user.username)
            db.add(db_user)
            db.commit()
            logger.info(f"Создан новый пользователь: {user.username}")
            await update.message.reply_text(f"👋 Привет, {user.username}! Я вас зарегистрировал.")
        else:
            await update.message.reply_text(f"👋 С возвращением, {user.username}!")
    await help_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справочное сообщение."""
    message = (
        "Я ваш ассистент по задачам. Доступные команды:\n\n"
        "/start - Начать работу\n"
        "/create_task - Создать новую задачу\n"
        "/my_tasks - Посмотреть ваши задачи\n"
        "/help - Показать эту справку"
    )
    await update.message.reply_text(message)


async def my_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает задачи пользователя."""
    user_id = update.effective_user.id
    logger.info(f"Запрос /my_tasks от пользователя {user_id}")

    with get_db_session() as db:
        tasks = db.query(Project).filter(Project.assignee_id == user_id).all()
        if not tasks:
            await update.message.reply_text("У вас пока нет назначенных задач.")
            return

        message_lines = ["📋 Ваши задачи:\n"]
        for task in tasks:
            message_lines.append(f"• ID: {task.id} - {task.project_name} (Статус: {task.status})")
        await update.message.reply_text("\n".join(message_lines))


# --- Логика создания задачи (ConversationHandler) ---

async def create_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога создания задачи."""
    # Пока создаем задачу только для себя для простоты.
    # Позже добавим выбор исполнителя.
    logger.info(f"Пользователь {update.effective_user.id} начал создавать задачу.")
    await update.message.reply_text(
        "Начинаем создание новой задачи.\n"
        "Введите название задачи (или /cancel для отмены):"
    )
    return TASK_NAME


async def get_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает название задачи и запрашивает количество дней."""
    context.user_data['task_name'] = update.message.text
    logger.info(f"Название задачи: {context.user_data['task_name']}")
    await update.message.reply_text("Сколько дней потребуется на выполнение? (введите число)")
    return TASK_DAYS


async def get_task_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает количество дней и начинает запрашивать план."""
    try:
        days = int(update.message.text)
        if not (1 <= days <= 30):
            raise ValueError
        context.user_data['task_days'] = days
        context.user_data['daily_plan'] = []
        context.user_data['current_day'] = 1
        logger.info(f"Количество дней: {days}")
        await update.message.reply_text(f"Отлично. Теперь введите план на День 1:")
        return TASK_DAY_CONTENT
    except (ValueError, TypeError):
        await update.message.reply_text("Пожалуйста, введите корректное число от 1 до 30.")
        return TASK_DAYS


async def get_day_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает план на день и либо запрашивает следующий, либо завершает."""
    plan = update.message.text
    context.user_data['daily_plan'].append(plan)
    
    current_day = context.user_data['current_day']
    total_days = context.user_data['task_days']
    
    if current_day < total_days:
        context.user_data['current_day'] += 1
        await update.message.reply_text(f"План на День {current_day} сохранен. Введите план на День {context.user_data['current_day']}:")
        return TASK_DAY_CONTENT
    else:
        logger.info("Введены все планы, сохраняем задачу...")
        return await save_task_and_finish(update, context)


async def save_task_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет задачу в БД и завершает диалог."""
    user_id = update.effective_user.id
    
    with get_db_session() as db:
        new_project = Project(
            project_name=context.user_data['task_name'],
            leader_id=user_id,
            assignee_id=user_id, # Пока назначаем на себя
            daily_plan=context.user_data['daily_plan']
        )
        db.add(new_project)
        db.commit()
        logger.info(f"Задача '{new_project.project_name}' создана для пользователя {user_id}")
        
        await update.message.reply_text(
            f"✅ Задача '{new_project.project_name}' успешно создана!\n"
            "Вы можете посмотреть ее в списке /my_tasks."
        )
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог."""
    logger.info(f"Пользователь {update.effective_user.id} отменил операцию.")
    context.user_data.clear()
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


# --- Конец логики диалога ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Логирует ошибки."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def main():
    """Основная функция для запуска бота."""
    logger.info("Инициализация...")
    create_db_and_tables()

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN не найден!")
        return

    application = Application.builder().token(token).build()

    # --- Создаем ConversationHandler ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create_task", create_task_start)],
        states={
            TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task_name)],
            TASK_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task_days)],
            TASK_DAY_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_day_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    # --- Добавляем обработчики ---
    application.add_handler(conv_handler) # Добавляем диалог
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("my_tasks", my_tasks_command))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
