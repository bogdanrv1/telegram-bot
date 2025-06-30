import logging
import os
from datetime import date

from contextlib import contextmanager
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes)

# Импортируем наши модели и функции для работы с БД
from database import SessionLocal, User, Project, create_db_and_tables

# --- Настройка ---
# Загружаем переменные окружения из файла .env
load_dotenv('.env')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Работа с базой данных ---
@contextmanager
def get_db_session():
    """Контекстный менеджер для безопасной работы с сессиями БД."""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

# --- Команды бота ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду /start.
    Регистрирует нового пользователя в базе данных, если его там нет.
    """
    user_id = update.effective_user.id
    username = update.effective_user.username
    logger.info(f"Команда /start от пользователя {username} ({user_id})")

    with get_db_session() as db:
        # Пытаемся найти пользователя в БД
        user = db.query(User).filter(User.id == user_id).first()
        
        # Если пользователя нет, создаем его
        if not user:
            user = User(id=user_id, username=username)
            db.add(user)
            db.commit()
            logger.info(f"Создан новый пользователь: {username} ({user_id})")
            await update.message.reply_text(f"👋 Привет, {username}! Я зарегистрировал тебя в системе.")
        else:
            await update.message.reply_text(f"👋 С возвращением, {username}!")

    await help_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справочное сообщение."""
    message = (
        "Я ваш ассистент по задачам. Вот что я умею:\n\n"
        "/start - Начать работу и зарегистрироваться\n"
        "/my_tasks - Посмотреть ваши задачи (пока в разработке)\n"
        "/help - Показать эту справку"
    )
    await update.message.reply_text(message)


async def my_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает задачи пользователя (демонстрация чтения из БД)."""
    user_id = update.effective_user.id
    logger.info(f"Запрос /my_tasks от пользователя {user_id}")

    with get_db_session() as db:
        # Ищем все задачи, назначенные этому пользователю
        tasks = db.query(Project).filter(Project.assignee_id == user_id).all()

        if not tasks:
            await update.message.reply_text("У вас пока нет назначенных задач.")
            return
        
        message_lines = ["📋 Ваши задачи:\n"]
        for task in tasks:
            message_lines.append(f"• ID: {task.id} - {task.project_name} (Статус: {task.status})")
        
        await update.message.reply_text("\n".join(message_lines))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки и выводит их в лог."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def main():
    """Основная функция для запуска бота."""
    
    # 1. Создаем таблицы в БД при запуске (безопасно для повторного вызова)
    logger.info("Проверка и создание таблиц в базе данных...")
    create_db_and_tables()
    logger.info("Таблицы готовы.")

    # 2. Получаем токен
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("Ошибка: Не найден TELEGRAM_TOKEN в переменных окружения")
        return

    # 3. Создаем и настраиваем приложение
    application = Application.builder().token(token).build()

    # 4. Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("my_tasks", my_tasks_command))

    # 5. Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # 6. Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    main()