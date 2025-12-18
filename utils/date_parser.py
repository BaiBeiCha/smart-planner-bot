import dateparser
from datetime import datetime
import pytz


class DateParserService:
    def __init__(self):
        self.base_settings = {
            'PREFER_DATES_FROM': 'future',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'SKIP_TOKENS': ['в', 'at', 'on', 'через', 'in'],
        }

    def parse_natural_text(self, text: str, user_timezone: str) -> datetime | None:
        if not text:
            return None

        try:
            settings = self.base_settings.copy()
            settings['TIMEZONE'] = user_timezone
            settings['TO_TIMEZONE'] = 'UTC'

            user_tz = pytz.timezone(user_timezone)
            user_now = datetime.now(user_tz)
            settings['RELATIVE_BASE'] = user_now

            return dateparser.parse(text, settings=settings, languages=['ru', 'en'])

        except Exception as e:
            print(f"Error parsing date '{text}': {e}")
            return None