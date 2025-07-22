from pydantic import BaseModel, EmailStr
from typing import List, Literal

class UserSignup(BaseModel):
    email: EmailStr
    password: str

class VerifyOTP(BaseModel):
    email: EmailStr
    otp: str

class Message(BaseModel):
    role:Literal['user', 'assistant']
    content:str

class RequestState(BaseModel):
    model_name: str
    model_provider: str
    system_prompt: str
    messages: list[Message]
    allow_search: bool