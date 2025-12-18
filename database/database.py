from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from config.settings import settings
from database.models import Base

class Database:
    def __init__(self):
        self.database_url = settings.DATABASE_URL
        self.async_engine = None
        self.async_session = None
    
    async def init_db(self):
        try:
            self.async_engine = create_async_engine(
                self.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
                echo=False
            )
            
            self.async_session = sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            async with self.async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            print("Database initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing database: {e}")
            return False
    
    def get_session(self):
        return self.async_session()
    
    async def close(self):
        if self.async_engine:
            await self.async_engine.dispose()

db = Database()