import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

# 1. Cryptographic Settings
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def get_password_hash(password: str) -> str:
    """Hashes a plaintext password using bcrypt and a randomly generated salt."""
    # Step A: Bcrypt requires raw bytes, so we encode the string
    pwd_bytes = password.encode('utf-8')

    # Step B: Generate a unique cryptographic salt
    salt = bcrypt.gensalt()

    # Step C: Hash the password combined with the salt
    hashed_password_bytes = bcrypt.hashpw(pwd_bytes, salt)

    # Step D: Decode back to a string so it can be saved in our SQLite database
    return hashed_password_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored hash."""
    # Bcrypt needs both the attempt and the stored hash to be in bytes
    password_attempt_bytes = plain_password.encode('utf-8')
    stored_hash_bytes = hashed_password.encode('utf-8')

    # bcrypt.checkpw automatically extracts the salt from the stored_hash_bytes and compares them
    return bcrypt.checkpw(password_attempt_bytes, stored_hash_bytes)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

from fastapi import WebSocketException, status
from jwt.exceptions import InvalidTokenError

# ... (keep all your existing code above) ...

def verify_ws_token(token: str):
    """Decodes the JWT to verify the user is authenticated before allowing WebSocket access."""
    try:
        # Attempt to decode the token using our secret master key
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
        return email
    except InvalidTokenError:
        # If the token is expired or forged, the math will fail, and we sever the connection
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Could not validate credentials")
