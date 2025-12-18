import sys
import subprocess
import shutil
from pathlib import Path

def check_python_version():
    if sys.version_info < (3, 8):
        print("❌ Ошибка: Требуется Python 3.8 или выше")
        print(f"Текущая версия: {sys.version}")
        sys.exit(1)
    print("✅ Версия Python совместима")

def create_env_file():
    env_file = Path(".env")
    example_file = Path(".env.example")
    
    if not env_file.exists() and example_file.exists():
        shutil.copy(example_file, env_file)
        print("✅ Файл .env создан из .env.example")
        print("⚠️  Не забудьте заполнить необходимые данные в файле .env!")
    elif env_file.exists():
        print("✅ Файл .env уже существует")
    else:
        print("❌ Файлы .env и .env.example не найдены")

def install_dependencies():
    print("📦 Установка зависимостей...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Зависимости установлены успешно")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при установке зависимостей: {e}")
        sys.exit(1)

def check_postgresql():
    print("🔍 Проверка PostgreSQL...")
    
    try:
        import asyncpg
        import sqlalchemy
        print("✅ Модули PostgreSQL доступны")
    except ImportError as e:
        print(f"❌ Ошибка импорта модулей PostgreSQL: {e}")
        print("Установите: pip install asyncpg sqlalchemy psycopg2-binary")
        sys.exit(1)

def create_database():
    print("🗄️ Проверка базы данных...")
    
    print("⚠️  Убедитесь, что база данных PostgreSQL создана и доступна")
    print("Команда для создания БД: CREATE DATABASE smart_planner_db;")

def check_docker():
    print("🐳 Проверка Docker...")
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Docker доступен")
        
        try:
            subprocess.run(["docker-compose", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("✅ Docker Compose доступен")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Docker Compose не найден. Установите Docker Compose для запуска в контейнерах.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Docker не найден. Для запуска в контейнерах установите Docker.")

def main():
    print("🚀 Начинаем установку Умного Планировщика v2.0...\n")
    
    check_python_version()
    print()
    
    create_env_file()
    print()
    
    install_dependencies()
    print()
    
    check_postgresql()
    print()
    
    create_database()
    print()
    
    check_docker()
    print()
    
    print("🎉 Установка завершена!")
    print("\nСледующие шаги:")
    print("1. Заполните файл .env своими данными")
    print("2. Создайте базу данных PostgreSQL (если не используете Docker)")
    print("3. Запустите бота:")
    print("   - Через Docker: docker-compose up -d")
    print("   - Локально: python main.py")
    print("\n📖 Подробная инструкция в файле README.md")
    print("\n🐳 Рекомендуется использовать Docker для простоты запуска!")

if __name__ == "__main__":
    main()