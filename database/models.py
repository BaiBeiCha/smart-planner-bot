from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    timezone = Column(String(50), nullable=False, default='Europe/Moscow')
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    created_groups = relationship("Group", back_populates="creator")

class Reminder(Base):
    __tablename__ = 'reminders'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    reminder_time = Column(DateTime, nullable=False)
    timezone = Column(String(50), nullable=False)
    is_recurring = Column(Boolean, default=False)
    recurring_pattern = Column(String(50))
    is_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="reminders")

class Group(Base):
    __tablename__ = 'groups'
    
    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    creator_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    creator = relationship("User", back_populates="created_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")

class GroupMember(Base):
    __tablename__ = 'group_members'
    
    id = Column(BigInteger, primary_key=True)
    group_id = Column(BigInteger, ForeignKey('groups.id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)
    
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")

class WeatherData(Base):
    __tablename__ = 'weather_data'
    
    id = Column(BigInteger, primary_key=True)
    city = Column(String(100), nullable=False)
    temperature = Column(Float)
    weather_condition = Column(String(50))
    humidity = Column(BigInteger)
    wind_speed = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)