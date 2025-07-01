import os
from dotenv import load_dotenv
from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, create_engine, DateTime, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)  # Telegram ID
    short_id = Column(Integer, unique=True, autoincrement=True)  # Короткий ID
    username = Column(String, nullable=True)
    display_name = Column(String(100), nullable=True)  # Пользовательский никнейм
    projects = relationship("Project", back_populates="user")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(10), unique=True, nullable=False)  # Уникальный 4-значный номер
    user_id = Column(BigInteger, ForeignKey("users.id"))
    name = Column(String(100), nullable=False)
    days_count = Column(Integer, nullable=False)
    reminder_time = Column(String(5), default="09:00")  # HH:MM
    status = Column(String(20), default="active")  # active, completed, paused
    created_at = Column(DateTime, default=datetime.utcnow)
    start_date = Column(DateTime, nullable=True)
    created_by = Column(BigInteger, nullable=True)
    user = relationship("User", back_populates="projects")
    daily_tasks = relationship("DailyTask", back_populates="project", cascade="all, delete-orphan")

class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    day_number = Column(Integer, nullable=False)  # День 1, 2, 3...
    description = Column(Text, nullable=False)
    completed = Column(String(20), default="pending")  # pending, completed, skipped
    completed_at = Column(DateTime, nullable=True)
    project = relationship("Project", back_populates="daily_tasks")

def create_tables():
    Base.metadata.create_all(bind=engine)

def generate_project_id():
    """Генерирует последовательный 4-значный номер проекта"""
    db = SessionLocal()
    try:
        # Получаем максимальный существующий ID
        max_project = db.query(Project).order_by(Project.project_id.desc()).first()
        if max_project:
            # Извлекаем число из строки ID и увеличиваем на 1
            try:
                next_id = int(max_project.project_id) + 1
            except ValueError:
                next_id = 1
        else:
            next_id = 1
        
        # Форматируем как 4-значное число с ведущими нулями
        return f"{next_id:04d}"
    finally:
        db.close()

if __name__ == "__main__":
    print("Создание таблиц...")
    create_tables()
    print("Готово.") 
