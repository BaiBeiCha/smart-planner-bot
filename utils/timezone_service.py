import pytz
from geopy.geocoders import Nominatim
from timezonefinderL import TimezoneFinder
import asyncio
from typing import Optional

class TimezoneService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="smart_planner_bot")
        self.tf = TimezoneFinder()
    
    async def get_timezone_by_city(self, city_name: str) -> Optional[str]:
        try:
            location = await asyncio.get_event_loop().run_in_executor(
                None, self.geolocator.geocode, city_name
            )
            
            if location:
                timezone_name = self.tf.timezone_at(lng=location.longitude, lat=location.latitude)
                return timezone_name
            else:
                return None
                
        except Exception as e:
            print(f"Error getting timezone for city {city_name}: {e}")
            return None
    
    def get_default_timezone(self) -> str:
        return 'Europe/Minsk'
    
    def convert_to_user_timezone(self, dt, user_timezone: str):
        try:
            if not user_timezone:
                user_timezone = self.get_default_timezone()
            
            utc = pytz.UTC
            user_tz = pytz.timezone(user_timezone)
            
            if dt.tzinfo is None:
                dt = utc.localize(dt)
            
            return dt.astimezone(user_tz)
        except Exception as e:
            print(f"Error converting timezone: {e}")
            return dt
    
    def convert_from_user_timezone(self, dt, user_timezone: str):
        try:
            if not user_timezone:
                user_timezone = self.get_default_timezone()
            
            user_tz = pytz.timezone(user_timezone)
            
            if dt.tzinfo is None:
                dt = user_tz.localize(dt)
            
            return dt.astimezone(pytz.UTC)
        except Exception as e:
            print(f"Error converting from user timezone: {e}")
            return dt