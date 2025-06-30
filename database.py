import os
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import (BigInteger, Column, Date, ForeignKey, Integer,
                        String, create_engine, Boolean)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Загружаем переменные окружения из файла .env
load_dotenv('.env')

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Необходимо установить переменную окружения DATABASE_URL")

# sqlalchemy engine
engine = create_engine(DATABASE_URL)
# Класс для создания сессий (подключений) к БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Базовый класс для всех моделей
Base = declarative_base()


# --- Модели (таблицы) ---

class User(Base):
    """Модель пользователя. Соответствует таблице 'users'."""
    __tablename__ = "users"

    # ID пользователя в Telegram. BigInteger, так как ID могут быть большими.
    id = Column(BigInteger, primary_key=True) 
    username = Column(String)
    reminder_time = Column(String, default="09:00")
    reminder_enabled = Column(Boolean, default=True)
    
    # Отношения: для удобного доступа к проектам пользователя
    led_projects = relationship("Project", back_populates="leader", foreign_keys="[Project.leader_id]")
    assigned_projects = relationship("Project", back_populates="assignee", foreign_keys="[Project.assignee_id]")


class Project(Base):
    """Модель проекта/задачи. Соответствует таблице 'projects'."""
    __tablename__ = "projects"

    # Уникальный ID проекта, генерируется автоматически
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String, index=True)
    
    # Внешние ключи к таблице пользователей
    leader_id = Column(BigInteger, ForeignKey("users.id"))
    assignee_id = Column(BigInteger, ForeignKey("users.id"))

    start_date = Column(Date, default=date.today)
    status = Column(String, default="active") # "active", "paused", "completed"
    daily_plan = Column(ARRAY(String), nullable=False)
    
    # Отношения: для удобного доступа к объектам User (руководитель и исполнитель)
    leader = relationship("User", back_populates="led_projects", foreign_keys=[leader_id])
    assignee = relationship("User", back_populates="assigned_projects", foreign_keys=[assignee_id])


# --- Функции для работы с БД ---

def get_db():
    """Создает сессию для запроса и закрывает ее после выполнения."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db_and_tables():
    """
    Создает все таблицы в базе данных на основе моделей.
    Эту функцию нужно будет запустить один раз при первом деплое.
    """
    print("Создание таблиц в базе данных...")
    Base.metadata.create_all(bind=engine)
    print("Таблицы успешно созданы.")

# Этот блок позволяет запустить создание таблиц вручную, 
# выполнив в терминале команду: python database.py
if __name__ == "__main__":
    create_db_and_tables() 