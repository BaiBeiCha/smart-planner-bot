import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
    DATABASE_URL = os.getenv('DATABASE_URL')
    ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
    
    WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
    WEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
    
    REMINDER_CHECK_INTERVAL = 60
    WEATHER_CHECK_INTERVAL = 3600
    
    DEFAULT_TIMEZONE = 'Europe/Minsk'
    
    IS_DOCKER = os.getenv('IS_DOCKER', 'false').lower() == 'true'

settings = Settings()