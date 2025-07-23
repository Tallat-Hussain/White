from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import random
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv()
import os



SECRET_KEY = "Your-Secret-Key-Here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)
def get_password_hash(password):
    return pwd_context.hash(password)
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_otp(email: str):
    return str(random.randint(100000, 999999))

def send_mail(receiver_email: str, otp:str):
    sender = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")

    msg =  EmailMessage()
    msg['Subject'] = 'Your OTP Code'
    msg['From'] = sender
    msg['To'] = receiver_email
    msg.set_content(f"Your OTP code is: {otp}, It will expire in 5 minutes.")
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
