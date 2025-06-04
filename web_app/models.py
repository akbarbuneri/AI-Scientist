import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text
from .db import Base

class RunStatus(str, enum.Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'

class Run(Base):
    __tablename__ = 'runs'
    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(RunStatus), default=RunStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    model_name = Column(String)
    experiment_name = Column(String)
    num_ideas = Column(Integer)
    template_slug = Column(String)
    output_directory = Column(String)
    error_message = Column(Text)
