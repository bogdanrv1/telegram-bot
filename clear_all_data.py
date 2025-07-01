#!/usr/bin/env python3
"""
Скрипт для полной очистки базы данных: удаляет всех пользователей, проекты и задачи.
"""
from database import SessionLocal, User, Project, DailyTask

def clear_all():
    db = SessionLocal()
    try:
        print("Удаляю все задачи...")
        db.query(DailyTask).delete()
        print("Удаляю все проекты...")
        db.query(Project).delete()
        print("Удаляю всех пользователей...")
        db.query(User).delete()
        db.commit()
        print("✅ Все пользователи, проекты и задачи удалены!")
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    confirm = input("ВНИМАНИЕ! Это удалит ВСЕ данные. Введите 'ДА' для подтверждения: ")
    if confirm.strip().upper() == 'ДА':
        clear_all()
    else:
        print("❌ Очистка отменена.") 