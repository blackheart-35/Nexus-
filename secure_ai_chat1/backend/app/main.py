import json
import os
import shutil
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, File, UploadFile, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

from . import models, schemas, security
from .database import engine, get_db, SessionLocal

# Create static folder for profile pictures automatically if it doesn't exist
os.makedirs("static", exist_ok=True)

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nexus Workspace API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (Profile pictures)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# USER REGISTRATION & AUTHENTICATION ENDPOINTS
# ==========================================

@app.post("/users/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Check if Email is already registered
    db_email = db.query(models.User).filter(models.User.email == user.email).first()
    if db_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is already registered. Please use another one."
        )

    # 2. Check if Username is already taken (Strict Uniqueness)
    db_username = db.query(models.User).filter(models.User.username == user.username).first()
    if db_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The username '@{user.username}' is already taken. Please choose a different handle."
        )

    hashed_pwd = security.get_password_hash(user.password)
    default_pfp = f"https://api.dicebear.com/7.x/identicon/svg?seed={user.username}"

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_pwd,
        profile_pic=default_pfp
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    access_token = security.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}

# ==========================================
# PROFILE MANAGEMENT ENDPOINTS
# ==========================================

@app.post("/profile/")
async def update_profile(
    token: str = Form(...),
    bio: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    email = security.verify_ws_token(token)
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.bio = bio
    if file:
        file_location = f"static/{user.username}_{file.filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        user.profile_pic = f"http://127.0.0.1:8000/{file_location}"

    db.commit()
    return {"status": "success", "bio": user.bio, "profile_pic": user.profile_pic}

@app.get("/profile/{username}")
def get_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"username": user.username, "bio": user.bio, "profile_pic": user.profile_pic}

@app.get("/messages/", response_model=list[schemas.MessageResponse])
def get_chat_history(db: Session = Depends(get_db)):
    return db.query(models.Message).order_by(models.Message.created_at.asc()).all()


# ==========================================
# ADVANCED WEBSOCKET ENGINE (Live Sync)
# ==========================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

    async def broadcast_active_users(self):
        users_list = list(self.active_connections.keys())
        msg = json.dumps({"type": "users_list", "users": users_list})
        await self.broadcast(msg)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    token: str = Query(...)
):
    email = security.verify_ws_token(token)
    await manager.connect(websocket, client_id)

    db = SessionLocal()
    user_pfp = "https://api.dicebear.com/7.x/identicon/svg?seed=default"
    try:
        current_user = db.query(models.User).filter(models.User.email == email).first()
        if current_user:
            user_pfp = current_user.profile_pic
    finally:
        db.close()

    try:
        join_msg = json.dumps({"type": "system", "content": f"User @{client_id} joined the secure relay."})
        await manager.broadcast(join_msg)
        await manager.broadcast_active_users()

        while True:
            data = await websocket.receive_text()

            # Save message to database
            db = SessionLocal()
            try:
                user = db.query(models.User).filter(models.User.email == email).first()
                if user:
                    new_message = models.Message(content=data, owner_id=user.id)
                    db.add(new_message)
                    db.commit()
            finally:
                db.close()

            current_time = datetime.now().strftime("%I:%M %p")

            chat_msg = json.dumps({
                "type": "chat",
                "sender": client_id,
                "content": data,
                "time": current_time,
                "pfp": user_pfp
            })
            await manager.broadcast(chat_msg)

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        leave_msg = json.dumps({"type": "system", "content": f"User @{client_id} disconnected."})
        await manager.broadcast(leave_msg)
        await manager.broadcast_active_users()
