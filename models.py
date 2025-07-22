from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timedelta

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    password = Column(String)

    chats = relationship("Chat", back_populates="user")
    uploaded_files = relationship("UploadedFile", back_populates="user")

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    messages = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="chats")
    uploaded_files = relationship("UploadedFile", back_populates="chat") 

class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String)
    file_type = Column(String)  
    extracted_text = Column(JSON)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"))
    chat_id = Column(Integer, ForeignKey("chats.id"))

    user = relationship("User", back_populates="uploaded_files")  
    chat = relationship("Chat", back_populates="uploaded_files") 


class OTP(Base):
    __tablename__ = 'otp'
    id=Column(Integer, primary_key=True, index=True)
    email=Column(String, index=True)
    otp=Column(String)
    expires_at=Column(DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=5))
    password = Column(String)

