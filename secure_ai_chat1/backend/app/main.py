from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, or_, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import json
import random
import requests

# --- 1. Real Email API Configuration (Brevo) ---
BREVO_API_KEY = "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"
SENDER_EMAIL = "nexususeradmin34@gmail.com"

# Temporary memory for OTPs
pending_otps = {}

# --- 2. Database Setup ---
DATABASE_URL = "sqlite:///./nexus.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 3. Database Models ---
class DBUser(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    bio = Column(Text, default="Hey! I am using Nexus.")

class DBFriendRequest(Base):
    __tablename__ = "friend_requests"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")

class DBPrivateMessage(Base):
    __tablename__ = "private_messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_username = Column(String)
    receiver_username = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- 4. FastAPI App Setup ---
app = FastAPI(title="Nexus Workspace - Real Emails")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 5. Schemas ---
class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class VerifyOTP(BaseModel):
    email: str
    otp: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class FriendReqAction(BaseModel):
    request_id: int
    action: str

class SendFriendReq(BaseModel):
    sender_username: str
    receiver_username: str

# --- 6. REAL EMAIL API LOGIC (Brevo) ---
def send_otp_email(receiver_email: str, otp_code: str):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    # Premium HTML Email Design
    payload = {
        "sender": {"name": "Nexus Security", "email": SENDER_EMAIL},
        "to": [{"email": receiver_email}],
        "subject": "Your Nexus Workspace OTP",
        "htmlContent": f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border-radius: 10px; background-color: #f3f4f6; max-width: 500px; margin: auto; border: 1px solid #e5e7eb;">
            <div style="text-align: center; margin-bottom: 20px;">
                <span style="font-size: 30px;">🌍</span>
                <h2 style="color: #2563eb; margin-top: 10px; margin-bottom: 0;">Welcome to Nexus!</h2>
            </div>
            <p style="color: #334155; text-align: center; font-size: 16px;">Your secure One-Time Password (OTP) to create your account is:</p>
            <div style="background-color: white; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; border: 2px dashed #cbd5e1;">
                <h1 style="margin: 0; letter-spacing: 8px; color: #1e293b; font-size: 32px;">{otp_code}</h1>
            </div>
            <p style="color: #64748b; font-size: 13px; text-align: center; margin-top: 20px;">This OTP is valid for a few minutes.<br>Do not share this code with anyone.</p>
        </div>
        """
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            return True, "Success"
        else:
            print(f"Brevo API Error: {response.text}")
            return False, response.text
    except Exception as e:
        print(f"Server Error: {str(e)}")
        return False, str(e)

# --- 7. Auth Routes ---
@app.post("/register/send-otp")
def register_send_otp(user: UserRegister, db: Session = Depends(get_db)):
    clean_email = user.email.strip().lower()

    if db.query(DBUser).filter(DBUser.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")
    if db.query(DBUser).filter(DBUser.email == clean_email).first():
        raise HTTPException(status_code=400, detail="This email is already registered.")

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Call Real Email API
    success, message = send_otp_email(clean_email, otp)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email. Server error.")

    pending_otps[clean_email] = otp
    return {"message": "OTP sent! Check your inbox."}

@app.post("/register/verify")
def verify_and_register(data: VerifyOTP, db: Session = Depends(get_db)):
    clean_email = data.email.strip().lower()

    if clean_email not in pending_otps or pending_otps[clean_email] != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    if db.query(DBUser).filter(DBUser.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username taken during verification.")

    new_user = DBUser(username=data.username, email=clean_email, password=data.password)
    db.add(new_user)
    db.commit()

    del pending_otps[clean_email]
    return {"message": "Account created successfully!"}

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(DBUser).filter(DBUser.username == user.username).first()
    if not db_user or db_user.password != user.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return {"message": "Login successful", "username": db_user.username}

# --- 8. Friend System Routes ---
@app.post("/friends/request/send")
def send_friend_request(req: SendFriendReq, db: Session = Depends(get_db)):
    sender = db.query(DBUser).filter(DBUser.username == req.sender_username).first()
    receiver = db.query(DBUser).filter(DBUser.username == req.receiver_username).first()
    if not receiver or sender.id == receiver.id:
        raise HTTPException(status_code=400, detail="User not found or invalid request")

    existing = db.query(DBFriendRequest).filter(
        or_(and_(DBFriendRequest.sender_id == sender.id, DBFriendRequest.receiver_id == receiver.id),
            and_(DBFriendRequest.sender_id == receiver.id, DBFriendRequest.receiver_id == sender.id))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Request pending or already friends")

    db.add(DBFriendRequest(sender_id=sender.id, receiver_id=receiver.id, status="pending"))
    db.commit()
    return {"message": "Friend request sent!"}

@app.get("/friends/requests/pending/{username}")
def get_pending_requests(username: str, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.username == username).first()
    if not user: return []
    requests = db.query(DBFriendRequest).filter(DBFriendRequest.receiver_id == user.id, DBFriendRequest.status == "pending").all()
    res = []
    for r in requests:
        s = db.query(DBUser).filter(DBUser.id == r.sender_id).first()
        res.append({"request_id": r.id, "sender_username": s.username})
    return res

@app.post("/friends/request/respond")
def respond_friend_request(action: FriendReqAction, db: Session = Depends(get_db)):
    req = db.query(DBFriendRequest).filter(DBFriendRequest.id == action.request_id).first()
    if not req: raise HTTPException(status_code=404, detail="Request not found")
    req.status = action.action
    db.commit()
    return {"message": f"Request {action.action}"}

@app.get("/friends/list/{username}")
def get_friends_list(username: str, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.username == username).first()
    if not user: return []
    accepted = db.query(DBFriendRequest).filter(
        or_(DBFriendRequest.sender_id == user.id, DBFriendRequest.receiver_id == user.id),
        DBFriendRequest.status == "accepted"
    ).all()
    friends = []
    for a in accepted:
        friend_id = a.receiver_id if a.sender_id == user.id else a.sender_id
        f_user = db.query(DBUser).filter(DBUser.id == friend_id).first()
        if f_user: friends.append({"id": f_user.id, "username": f_user.username})
    return friends

@app.get("/messages/private/{user1}/{user2}")
def get_private_history(user1: str, user2: str, db: Session = Depends(get_db)):
    messages = db.query(DBPrivateMessage).filter(
        or_(and_(DBPrivateMessage.sender_username == user1, DBPrivateMessage.receiver_username == user2),
            and_(DBPrivateMessage.sender_username == user2, DBPrivateMessage.receiver_username == user1))
    ).order_by(DBPrivateMessage.timestamp.asc()).all()
    return [{"sender": m.sender_username, "receiver": m.receiver_username, "content": m.content} for m in messages]

# --- 9. WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_global: List[WebSocket] = []
        self.private_connections: Dict[str, WebSocket] = {}

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.active_global.append(websocket)

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.active_global: self.active_global.remove(websocket)

    async def broadcast_global(self, message: str):
        for connection in self.active_global: await connection.send_text(message)

    async def connect_private(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.private_connections[username] = websocket

    def disconnect_private(self, username: str):
        if username in self.private_connections: del self.private_connections[username]

    async def send_private(self, sender: str, receiver: str, content: str, db: Session):
        db.add(DBPrivateMessage(sender_username=sender, receiver_username=receiver, content=content))
        db.commit()
        message_data = json.dumps({"sender": sender, "receiver": receiver, "content": content})
        if receiver in self.private_connections: await self.private_connections[receiver].send_text(message_data)
        if sender in self.private_connections: await self.private_connections[sender].send_text(message_data)

manager = ConnectionManager()

@app.websocket("/ws")
async def global_websocket(websocket: WebSocket):
    await manager.connect_global(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast_global(data)
    except WebSocketDisconnect:
        manager.disconnect_global(websocket)

@app.websocket("/ws/private/{username}")
async def private_websocket(websocket: WebSocket, username: str):
    await manager.connect_private(username, websocket)
    db = SessionLocal()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("receiver") and data.get("content"):
                await manager.send_private(username, data["receiver"], data["content"], db)
    except WebSocketDisconnect:
        manager.disconnect_private(username)
    finally:
        db.close()
