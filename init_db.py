# init_db.py
from models import Base
from database import engine
from models import User, Chat  # force import models

print("📦 Creating tables in PostgreSQL...")
Base.metadata.create_all(bind=engine)
print("✅ Done: Tables created.")
