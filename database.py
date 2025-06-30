import os
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import (BigInteger, Boolean, Column, Date, ForeignKey, Integer,
                        String, create_engine)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Загружаем переменные окружения из файла .env для локального запуска
load_dotenv()

# --- Настройка подключения к БД ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Эта ошибка сработает, если вы забудете настроить переменные на Render
    # или создать .env файл локально.
    raise ValueError("Необходимо установить переменную окружения DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Модели таблиц ---

class User(Base):
    """Модель пользователя (таблица 'users')."""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True) # ID из Telegram
    username = Column(String, nullable=True)
    reminder_time = Column(String, default="09:00")
    reminder_enabled = Column(Boolean, default=True)
    
    # Связи для удобных запросов (не создают реальных колонок)
    led_projects = relationship("Project", back_populates="leader", foreign_keys="[Project.leader_id]")
    assigned_projects = relationship("Project", back_populates="assignee", foreign_keys="[Project.assignee_id]")


class Project(Base):
    """Модель проекта/задачи (таблица 'projects')."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True) # Уникальный ID задачи
    project_name = Column(String, nullable=False)
    
    leader_id = Column(BigInteger, ForeignKey("users.id"))
    assignee_id = Column(BigInteger, ForeignKey("users.id"))

    start_date = Column(Date, default=date.today)
    status = Column(String, default="active")
    daily_plan = Column(ARRAY(String), nullable=False)
    
    leader = relationship("User", back_populates="led_projects", foreign_keys=[leader_id])
    assignee = relationship("User", back_populates="assigned_projects", foreign_keys=[assignee_id])


# --- Функции для управления БД ---

def create_db_and_tables():
    """
    Создает все таблицы в базе данных, если их еще не существует.
    Безопасна для многократного вызова.
    """
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    # Этот блок позволяет создать таблицы вручную, если запустить файл напрямую:
    # python database.py
    print("Создание таблиц в базе данных...")
    create_db_and_tables()
    print("Таблицы успешно созданы.") 