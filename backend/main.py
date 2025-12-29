"""
NullTale Backend - FastAPI Server
Provides API endpoints for the NullTale AI personality chat application.
"""

import os
import uuid
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="NullTale API", version="1.0.0")

# CORS middleware for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "text").mkdir(exist_ok=True)
(UPLOAD_DIR / "video").mkdir(exist_ok=True)
(UPLOAD_DIR / "voice").mkdir(exist_ok=True)

# In-memory storage (would use a database in production)
sessions_db = {
    "1": {"id": "1", "name": "Alan Turing", "preview": "The imitation game is..."},
    "2": {"id": "2", "name": "Ada Lovelace", "preview": "Calculating the numbers..."},
    "3": {"id": "3", "name": "Marcus Aurelius", "preview": "The obstacle is the way."},
}

messages_db = {
    "1": [
        {
            "id": "msg-1",
            "role": "assistant",
            "content": "Hello. I am initialized with the cognitive patterns of Alan Turing. How may I assist in your computations today?",
            "timestamp": "10:23 AM"
        }
    ]
}

settings_db = {
    "model_version": "v2.4",
    "temperature": 0.7,
    "api_key": "sk-........................"
}

# AI Response templates for mock responses
AI_RESPONSES = [
    "That is a fascinating query. It reminds me of the halting problem...",
    "Indeed, this is similar to what I pondered during my work at Bletchley Park.",
    "The logical structure of your question is quite interesting.",
    "Let me process that through my neural patterns...",
    "Ah, this brings to mind certain mathematical principles.",
    "A most intriguing proposition. Let me elaborate.",
]


# --- Models ---
class ChatMessage(BaseModel):
    content: str
    session_id: str = "1"


class SessionCreate(BaseModel):
    name: str


class SettingsUpdate(BaseModel):
    model_version: Optional[str] = None
    temperature: Optional[float] = None
    api_key: Optional[str] = None


# --- Chat Endpoints ---
@app.post("/api/chat")
async def send_message(message: ChatMessage):
    """Send a message and get an AI response."""
    session_id = message.session_id
    
    if session_id not in messages_db:
        messages_db[session_id] = []
    
    # Create user message
    timestamp = datetime.now().strftime("%I:%M %p")
    user_msg = {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "user",
        "content": message.content,
        "timestamp": timestamp
    }
    messages_db[session_id].append(user_msg)
    
    # Generate mock AI response
    ai_response = random.choice(AI_RESPONSES)
    ai_msg = {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "assistant",
        "content": ai_response,
        "timestamp": datetime.now().strftime("%I:%M %p")
    }
    messages_db[session_id].append(ai_msg)
    
    # Update session preview
    if session_id in sessions_db:
        sessions_db[session_id]["preview"] = message.content[:30] + "..."
    
    return {"user_message": user_msg, "ai_message": ai_msg}


@app.get("/api/messages/{session_id}")
async def get_messages(session_id: str):
    """Get all messages for a session."""
    return {"messages": messages_db.get(session_id, [])}


# --- Session Endpoints ---
@app.get("/api/sessions")
async def get_sessions():
    """Get all chat sessions."""
    return {"sessions": list(sessions_db.values())}


@app.post("/api/sessions")
async def create_session(session: SessionCreate):
    """Create a new chat session (New Null)."""
    session_id = str(uuid.uuid4().hex[:8])
    new_session = {
        "id": session_id,
        "name": session.name,
        "preview": "New conversation started..."
    }
    sessions_db[session_id] = new_session
    
    # Initialize with welcome message
    messages_db[session_id] = [{
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "assistant",
        "content": f"Hello. I am now initialized as {session.name}. How may I assist you?",
        "timestamp": datetime.now().strftime("%I:%M %p")
    }]
    
    return new_session


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del sessions_db[session_id]
    if session_id in messages_db:
        del messages_db[session_id]
    
    return {"success": True, "deleted_id": session_id}


# --- File Upload Endpoints ---
@app.post("/api/files/{file_type}")
async def upload_file(file_type: str, file: UploadFile = File(...)):
    """Upload a file to the knowledge base (text, video, or voice)."""
    if file_type not in ["text", "video", "voice"]:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix if file.filename else ""
    unique_name = f"{uuid.uuid4().hex}{file_ext}"
    file_path = UPLOAD_DIR / file_type / unique_name
    
    # Save file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    return {
        "success": True,
        "filename": file.filename,
        "saved_as": unique_name,
        "file_type": file_type,
        "size": len(content)
    }


@app.get("/api/files/{file_type}")
async def list_files(file_type: str):
    """List uploaded files by type."""
    if file_type not in ["text", "video", "voice"]:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    folder = UPLOAD_DIR / file_type
    files = [f.name for f in folder.iterdir() if f.is_file()]
    return {"files": files, "count": len(files)}


# --- AI Refresh Endpoint ---
@app.post("/api/refresh")
async def refresh_ai_memory():
    """Trigger AI memory reindexing (mock implementation)."""
    return {
        "success": True,
        "message": "Neural patterns reindexed successfully",
        "files_processed": {
            "text": len(list((UPLOAD_DIR / "text").iterdir())),
            "video": len(list((UPLOAD_DIR / "video").iterdir())),
            "voice": len(list((UPLOAD_DIR / "voice").iterdir()))
        }
    }


# --- Settings Endpoints ---
@app.get("/api/settings")
async def get_settings():
    """Get current AI settings."""
    return settings_db


@app.put("/api/settings")
async def update_settings(settings: SettingsUpdate):
    """Update AI settings."""
    if settings.model_version:
        settings_db["model_version"] = settings.model_version
    if settings.temperature is not None:
        settings_db["temperature"] = settings.temperature
    if settings.api_key:
        settings_db["api_key"] = settings.api_key
    
    return {"success": True, "settings": settings_db}


if __name__ == "__main__":
    import uvicorn
    print("Starting NullTale Backend on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
