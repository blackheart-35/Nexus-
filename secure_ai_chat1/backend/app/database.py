from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database file location
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

# engine manages the connection to the database
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# SessionLocal is the factory for creating database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the class that our models inherit from
Base = declarative_base()

# NEW: The missing function that main.py was looking for
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
