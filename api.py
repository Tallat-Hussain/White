import auth
from datetime import datetime, timedelta
import models
import schemas
from schemas import Message, RequestState
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import User, Chat, UploadedFile, OTP
from database import get_db, SessionLocal, engine, Base
import uvicorn
from typing import List, Optional
from auth import SECRET_KEY, ALGORITHM, create_access_token, verify_password, get_password_hash
from jose import jwt, JWTError
from ai import get_respoonse, get_head_model_response
from pydantic import BaseModel
from typing import Literal
import fitz
from PIL import Image
import pytesseract
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# filepath: d:\testing\api.py
import io

Base.metadata.create_all(bind=engine)

app = FastAPI(title='LangGraph AI Backend')
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db_session)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

@app.post("/signup")
def signup(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.username == form.username).first()
    if user:
        raise HTTPException(status_code=400, detail="Username already registered")

    otp = auth.generate_otp(form.username)
    auth.send_mail(form.username, otp)
    expires = datetime.utcnow() + timedelta(minutes=5)

    hashed_pw = get_password_hash(form.password)

    otp_entry = models.OTP(
        email=form.username,
        otp=otp,
        expires_at=expires,
        password=hashed_pw
    )
    db.add(otp_entry)
    db.commit()

    return {"message": "OTP sent to your email."}

@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/verify-token")
def verify_token(payload: dict = Body(...), db: Session = Depends(get_db_session)):
    token = payload.get("token")
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"valid": True}
    except JWTError:
        return {"valid": False}

class ChatMessagePayload(BaseModel):
    message: str
    chat_id: Optional[int] = None

async def call_llm_for_title_generation(first_message_content: str) -> str:
    try:
        clean_message = first_message_content.replace("User:", "").strip()
        
        if not clean_message:
            return "New Chat"

        title_prompt_messages = [
            {"role": "system", "content": "You are a title generation assistant. Summarize the following user input into a concise, 5-10 word title. Do not include quotes or special characters. Respond only with the title."},
            {"role": "user", "content": clean_message}
        ]
        
        response_obj = get_respoonse(
            model_name="gemini-2.0-flash",
            messages=title_prompt_messages,
            allow_search=False,
            system_prompt="Generate a concise chat title.",
            provider="Gemini"
        )
        
        generated_title = response_obj.get("response", "New Chat").strip()

        if len(generated_title.split()) > 10:
            generated_title = " ".join(generated_title.split()[:10]) + "..."
        
        return generated_title

    except Exception as e:
        # In a production environment, you might log this error instead of printing
        print(f"Error generating title with LLM: {e}")
        return "New Chat"

@app.post("/chat")
async def save_chat(
    payload: ChatMessagePayload,
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    chat_id = payload.chat_id
    message_content = payload.message

    if chat_id is None:
        new_chat_title = await call_llm_for_title_generation(message_content)

        chat = Chat(
            messages=message_content,
            user_id=user.id,
            title=new_chat_title,
            timestamp=datetime.utcnow()
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

        return {"msg": "New chat created and message saved", "chat_id": chat.id, "title": chat.title}
    else:
        chat = db.query(Chat).filter(
            Chat.id == chat_id,
            Chat.user_id == user.id
        ).first()

        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        chat.messages = f"{chat.messages}\n{message_content}"
        chat.timestamp = datetime.utcnow()

        db.commit()
        db.refresh(chat)

        return {"msg": "Message appended to chat", "chat_id": chat.id, "title": chat.title}

@app.get("/history", response_model=List[dict])
def get_history(user=Depends(get_current_user), db: Session = Depends(get_db_session)):
    chats = db.query(Chat).filter(Chat.user_id == user.id).all()
    return [{"id": c.id, "title": c.title, "messages": c.messages, "timestamp": c.timestamp.isoformat()} for c in chats]

@app.delete("/history/{chat_id}")
def delete_chat(chat_id: int, user=Depends(get_current_user), db: Session = Depends(get_db_session)):
    chat = db.query(Chat).filter(Chat.id == chat_id,
                                 Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.delete(chat)
    db.commit()
    return {"msg": "Chat deleted"}

@app.put("/history/{chat_id}/rename")
def rename_chat(chat_id: int, new_title: str, user=Depends(get_current_user), db: Session = Depends(get_db_session)):
    chat = db.query(Chat).filter(Chat.id == chat_id,
                                 Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.title = new_title
    db.commit()
    db.refresh(chat)
    return {"msg": "Chat renamed", "new_title": chat.title}

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RequestState(BaseModel):
    model_name: str
    model_provider: str
    system_prompt: str
    messages: List[Message]
    allow_search: bool

ALLOWED_MODEL_NAMES = ['llama3-70b-8192', 'llama-3.3-70b-versatile',
                       "gemini-2.0-flash", "mistralai/Mixtral-8x7B-Instruct-v0.1"]

@app.post('/chat-ai')
def chat_endpoint(request: RequestState):
    try:
        allow_search = request.allow_search
        system_prompt = request.system_prompt

        if request.model_provider == "White-Fusion":
            response = get_head_model_response(
                request.messages, allow_search, system_prompt)
        else:
            if request.model_name not in ALLOWED_MODEL_NAMES:
                return {'error': 'Model not supported'}

            llm_id = request.model_name
            provider = request.model_provider
            response = get_respoonse(
                llm_id, request.messages, allow_search, system_prompt, provider)

        return response

    except Exception as e:
        return {"error": str(e)}

@app.post("/verify-otp")
def verify_otp(data: schemas.VerifyOTP, db: Session = Depends(get_db_session)):
    otp_entry = (
        db.query(models.OTP)
        .filter(models.OTP.email == data.email)
        .order_by(models.OTP.expires_at.desc())
        .first()
    )

    if not otp_entry:
        raise HTTPException(status_code=404, detail="No OTP found.")
    if otp_entry.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired.")
    if otp_entry.otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    existing_user = db.query(models.User).filter(models.User.username == data.email).first()
    if existing_user:
        return {"message": "User already verified."}

    new_user = models.User(
        username=data.email,
        email=data.email,
        password=otp_entry.password
    )
    db.add(new_user)
    db.commit()

    db.delete(otp_entry)
    db.commit()

    return {"message": "Email successfully verified and user created!"}

@app.post("/resend-otp")
def resend_otp(email: str = Body(..., embed=True), db: Session = Depends(get_db_session)):
    user_check = db.query(models.User).filter(models.User.email == email).first()
    if user_check:
        raise HTTPException(status_code=400, detail="User already registered and verified. Please login.")

    existing_otp_entry = db.query(models.OTP).filter(models.OTP.email == email).first()
    if existing_otp_entry and existing_otp_entry.expires_at > datetime.utcnow() - timedelta(seconds=30):
        raise HTTPException(status_code=400, detail="Please wait before resending OTP.")
    
    otp = auth.generate_otp(email)
    auth.send_mail(email, otp)

    if existing_otp_entry:
        existing_otp_entry.otp = otp
        existing_otp_entry.expires_at = datetime.utcnow() + timedelta(minutes=5)
    else:
        raise HTTPException(status_code=400, detail="No pending signup found for this email. Please sign up first.")
        
    db.commit()
    return {"message": "New OTP sent to your email."}

@app.post("/upload-pdf-to-chat/")
async def upload_pdf_to_chat(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File is not a PDF.")

    contents = await file.read()
    doc = fitz.open(stream=contents, filetype="pdf")

    raw_text_pages = []

    for page in doc:
        text = page.get_text().strip()

        if not text:
            pix = page.get_pixmap()
            img = Image.open(io.BytesIO(pix.tobytes()))
            text = pytesseract.image_to_string(img)

        raw_text_pages.append(text)

    json_text = {"pages": raw_text_pages}
    full_text = "\n".join(raw_text_pages)

    chat = Chat(
        title=f"PDF: {file.filename[:50]}", # Placeholder title, consider using LLM to summarize PDF content for title
        messages=full_text,
        user_id=user.id,
        timestamp=datetime.utcnow()
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    uploaded_file = UploadedFile(
        file_name=file.filename,
        file_type="pdf",
        extracted_text=json_text,
        user_id=user.id,
        chat_id=chat.id,
        uploaded_at=datetime.utcnow()
    )
    db.add(uploaded_file)
    db.commit()

    return {
        "msg": "PDF uploaded and stored with chat",
        "chat_id": chat.id,
        "file_id": uploaded_file.id,
        "extracted_text": json_text
    }

@app.post("/upload-image-to-chat/")
async def upload_image_to_chat(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    try:
        image = Image.open(io.BytesIO(await file.read()))
        text = pytesseract.image_to_string(image)

        chat = Chat(
            title=f"Image: {file.filename[:50]}", # Placeholder title, consider using LLM to summarize image content for title
            messages=text,
            user_id=user.id,
            timestamp=datetime.utcnow()
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        
        uploaded_file = UploadedFile(
            file_name=file.filename,
            file_type="image",
            extracted_text=text,
            user_id=user.id,
            chat_id=chat.id,
            uploaded_at=datetime.utcnow()
        )
        db.add(uploaded_file)
        db.commit()

        return {
            "msg": "Image uploaded and stored with chat",
            "chat_id": chat.id,
            "file_id": uploaded_file.id,
            "extracted_text": text
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)