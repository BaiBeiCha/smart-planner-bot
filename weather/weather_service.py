from typing import Any
import aiohttp
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from config.settings import settings
from database.database import db
from database.models import WeatherData

class WeatherService:
    def __init__(self):
        self.api_key = settings.OPENWEATHER_API_KEY
        self.base_url = settings.WEATHER_API_URL
        self.forecast_url = settings.WEATHER_FORECAST_URL
        self.cache_duration = timedelta(seconds=settings.WEATHER_CHECK_INTERVAL)

    async def get_current_weather(self, city: str) -> dict[str, Any] | None:
        cached_weather = await self.get_cached_weather(city)
        if cached_weather:
            return cached_weather

        try:
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        weather_data = {
                            'temperature': data['main']['temp'],
                            'description': data['weather'][0]['description'],
                            'humidity': data['main']['humidity'],
                            'wind_speed': data['wind']['speed'],
                            'condition': data['weather'][0]['main'].lower()
                        }

                        await self.save_weather_data(city, data)
                        return weather_data
                    else:
                        print(f"Weather API error: {response.status}")
                        return None
        except Exception as e:
            print(f"Error getting weather data: {e}")
            return None

    async def get_cached_weather(self, city: str) -> dict[str, Any] | None:
        try:
            async with db.get_session() as session:
                stmt = select(WeatherData).filter_by(city=city).order_by(WeatherData.timestamp.desc()).limit(1)
                weather_record = await session.scalar(stmt)

                if weather_record:
                    if datetime.utcnow() - weather_record.timestamp < self.cache_duration:
                        return {
                            'temperature': weather_record.temperature,
                            'description': weather_record.weather_condition,
                            'humidity': weather_record.humidity,
                            'wind_speed': weather_record.wind_speed,
                            'condition': weather_record.weather_condition
                        }
                    else:
                        await self.cleanup_old_weather(city)
        except Exception as e:
            print(f"Error checking cached weather: {e}")
        return None

    async def save_weather_data(self, city: str, data: dict):
        try:
            async with db.get_session() as session:
                await session.execute(delete(WeatherData).where(WeatherData.city == city))

                weather_record = WeatherData(
                    city=city,
                    temperature=data['main']['temp'],
                    weather_condition=data['weather'][0]['main'].lower(),
                    humidity=data['main']['humidity'],
                    wind_speed=data['wind']['speed'],
                    timestamp=datetime.utcnow()
                )
                session.add(weather_record)
                await session.commit()
        except Exception as e:
            print(f"Error saving weather data: {e}")

    async def cleanup_old_weather(self, city: str):
        try:
            async with db.get_session() as session:
                await session.execute(delete(WeatherData).where(WeatherData.city == city))
                await session.commit()
        except Exception:
            pass

    async def get_weather_forecast(self, city: str, hours_ahead: int = 24) -> list:
        try:
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.forecast_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        forecast = []
                        current_time = datetime.now()
                        target_time = current_time + timedelta(hours=hours_ahead)

                        for item in data['list']:
                            forecast_time = datetime.fromtimestamp(item['dt'])
                            if forecast_time <= target_time:
                                forecast.append({
                                    'time': forecast_time,
                                    'temperature': item['main']['temp'],
                                    'description': item['weather'][0]['description'],
                                    'condition': item['weather'][0]['main'].lower(),
                                    'humidity': item['main']['humidity'],
                                    'wind_speed': item['wind']['speed']
                                })

                        return forecast
                    else:
                        print(f"Weather forecast API error: {response.status}")
                        return []
        except Exception as e:
            print(f"Error getting weather forecast: {e}")
            return []

    def get_time_of_day(self, hour: int = None) -> str:
        if hour is None:
            hour = datetime.now().hour

        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

    async def get_weather_recommendation(self, city: str, time_of_day: str = None) -> str:
        current_weather = await self.get_current_weather(city)

        if not current_weather:
            return "Не удалось получить данные о погоде."

        temperature = current_weather['temperature']
        condition = current_weather['condition']

        recommendations = []

        if temperature < -10:
            recommendations.append("Очень холодно! Одевайтесь очень тепло.")
        elif temperature < 0:
            recommendations.append("Холодно! Не забудьте шапку и перчатки.")
        elif temperature < 10:
            recommendations.append("Прохладно! Лучше взять куртку.")
        elif temperature > 30:
            recommendations.append("Жарко! Пейте больше воды.")
        elif temperature > 25:
            recommendations.append("Тепло! Отличная погода для прогулки.")

        if 'rain' in condition or 'drizzle' in condition:
            recommendations.append("Идет дождь! Возьмите зонт.")
        elif 'snow' in condition:
            recommendations.append("Идет снег! Будьте осторожны на дороге.")
        elif 'clear' in condition and time_of_day == 'morning':
            recommendations.append("Солнечное утро! Отличный день для активностей.")
        elif 'fog' in condition or 'mist' in condition:
            recommendations.append("Туман! Будьте внимательны на дороге.")

        if time_of_day == 'evening' and temperature < 15:
            recommendations.append("Вечером похолодает! Возьмите теплую одежду.")

        return " ".join(recommendations) if recommendations else "Хорошего дня!"