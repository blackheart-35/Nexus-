from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

# FastAPI App Initialize
app = FastAPI(title="Nexus Workspace API")

# 1. CORS Middleware - Yeh phone aur Vercel se aane wali requests ko block hone se rokega
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Har jagah se connection allow karega
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Root Endpoint - Yeh Render ko 404 error dene se rokega aur server ko hamesha zinda rakhega
@app.get("/")
def read_root():
    return {"status": "Nexus Server is Active and Healthy!"}

# --- Dummy Database & Auth (Agar aap apne frontend se login/register bhej rahe hain) ---
users_db = {}

class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: UserRegister):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="User already exists")
    users_db[user.username] = user.password
    return {"message": "User registered successfully"}

@app.post("/login")
def login(user: UserLogin):
    if user.username not in users_db or users_db[user.username] != user.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return {"message": "Login successful", "username": user.username}

# --- WebSocket Setup (Dosto ke sath chat / Global Relay ke liye) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Jaise hi ek user message bhejega, sabko broadcast ho jayega
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
