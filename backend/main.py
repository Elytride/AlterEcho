"""
NullTale Backend - FastAPI Server
Provides API endpoints for the NullTale AI personality chat application.
Features: Gemini 2.5 Flash Lite AI, Streaming Voice Synthesis
"""

import os
import sys
import json
import uuid
import base64
import random
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai

# Add Voice Testing to path for WaveSpeedManager import
VOICE_TESTING_PATH = Path(__file__).parent / "Voice Testing"
sys.path.insert(0, str(VOICE_TESTING_PATH))
from wavespeed_manager import WaveSpeedManager

app = FastAPI(title="NullTale API", version="1.0.0")

# CORS middleware for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Gemini
CREDENTIALS_PATH = Path(__file__).parent / "credentials"
cred_files = list(CREDENTIALS_PATH.glob("*.json"))
if cred_files:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_files[0])

# Try to get API key from environment or use default config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model (lazy load)
_gemini_model = None
def get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel("gemini-2.5-flash-lite")
    return _gemini_model

# Warmup flag to prevent multiple simultaneous warmups
_warming_up = False

@app.post("/api/warmup")
async def warmup_models():
    """
    Preload Gemini model in background.
    Call this when user clicks Call button to reduce first response latency.
    """
    global _warming_up
    if _warming_up:
        return {"status": "already_warming"}
    
    _warming_up = True
    try:
        # Load Gemini model
        print("Warming up Gemini model...")
        model = get_gemini_model()
        
        print("Warmup complete!")
        return {"status": "ready"}
    except Exception as e:
        print(f"Warmup error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        _warming_up = False

# Create uploads directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "text").mkdir(exist_ok=True)
(UPLOAD_DIR / "video").mkdir(exist_ok=True)
(UPLOAD_DIR / "voice").mkdir(exist_ok=True)

# Create data directory for persistence
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# File paths for persistent storage
SESSIONS_FILE = DATA_DIR / "sessions.json"
MESSAGES_FILE = DATA_DIR / "messages.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

def load_json(file_path: Path, default: dict) -> dict:
    """Load data from JSON file, or return default if not exists."""
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")
    return default

def save_json(file_path: Path, data: dict):
    """Save data to JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save {file_path}: {e}")

# Default data
DEFAULT_SESSIONS = {
    "1": {
        "id": "1", 
        "name": "Alan Turing", 
        "preview": "The imitation game is...",
        "system_prompt": "You are Alan Turing, the brilliant mathematician and computer scientist. Speak with intellectual curiosity, reference your work on computation and the Enigma machine. Be thoughtful and precise in your responses. Keep responses concise for voice synthesis (2-3 sentences max).",
        "voice": "test_voice",
        "wavespeed_voice_id": None,
        "voice_created_at": None,
        "voice_last_used_at": None
    }
}

DEFAULT_MESSAGES = {
    "1": [
        {
            "id": "msg-1",
            "role": "assistant",
            "content": "Hello. I am initialized with the cognitive patterns of Alan Turing. How may I assist in your computations today?",
            "timestamp": "10:23 AM"
        }
    ]
}

DEFAULT_SETTINGS = {
    "model_version": "gemini-2.5-flash-lite",
    "temperature": 0.7,
    "api_key": "configured",
    "wavespeed_api_key": ""
}

# Load persistent data (or use defaults)
sessions_db = load_json(SESSIONS_FILE, DEFAULT_SESSIONS)
messages_db = load_json(MESSAGES_FILE, DEFAULT_MESSAGES)
settings_db = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)

def save_sessions():
    """Save sessions to disk."""
    save_json(SESSIONS_FILE, sessions_db)

def save_messages():
    """Save messages to disk."""
    save_json(MESSAGES_FILE, messages_db)

def save_settings():
    """Save settings to disk."""
    save_json(SETTINGS_FILE, settings_db)


# --- Knowledge Base & Context Helpers ---
def load_knowledge_base() -> str:
    """
    Load all text files from the knowledge base to include in AI context.
    Returns concatenated content from all uploaded text files.
    """
    knowledge_content = []
    text_folder = UPLOAD_DIR / "text"
    
    if not text_folder.exists():
        return ""
    
    for file_path in text_folder.iterdir():
        if file_path.is_file():
            try:
                # Try common text encodings
                content = None
                for encoding in ['utf-8', 'utf-16', 'latin-1']:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content:
                    # Limit each file to ~2000 chars to avoid token limits
                    if len(content) > 2000:
                        content = content[:2000] + "\n... [truncated]"
                    knowledge_content.append(f"=== {file_path.name} ===\n{content}")
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")
    
    if not knowledge_content:
        return ""
    
    return "\n\n".join(knowledge_content)


def build_conversation_context(session_id: str, max_history: int = 10) -> str:
    """
    Build conversation history context for the AI.
    Returns formatted string of recent messages.
    """
    messages = messages_db.get(session_id, [])
    if not messages:
        return ""
    
    # Get last N messages
    recent = messages[-max_history:]
    
    context_parts = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "You"
        context_parts.append(f"{role}: {msg['content']}")
    
    return "\n".join(context_parts)


def build_full_prompt(session_id: str, user_message: str, system_prompt: str) -> str:
    """
    Build the complete prompt including:
    1. System prompt (personality)
    2. Knowledge base content
    3. Conversation history
    4. Current user message
    """
    parts = [system_prompt]
    
    # Add knowledge base if available
    knowledge = load_knowledge_base()
    if knowledge:
        parts.append(f"\n\n=== KNOWLEDGE BASE (Use this information to inform your responses) ===\n{knowledge}\n=== END KNOWLEDGE BASE ===")
    
    # Add conversation history
    history = build_conversation_context(session_id, max_history=10)
    if history:
        parts.append(f"\n\n=== CONVERSATION HISTORY ===\n{history}\n=== END HISTORY ===")
    
    # Add current message
    parts.append(f"\n\nUser: {user_message}\n\nRespond naturally while staying in character. Use knowledge from the knowledge base when relevant:")
    
    return "".join(parts)


# --- Models ---
class ChatMessage(BaseModel):
    content: str
    session_id: str = "1"


class CallMessage(BaseModel):
    content: str
    session_id: str = "1"


class SessionCreate(BaseModel):
    name: str


class SettingsUpdate(BaseModel):
    model_version: Optional[str] = None
    temperature: Optional[float] = None
    api_key: Optional[str] = None
    wavespeed_api_key: Optional[str] = None


# --- Chat Endpoints (Text Mode) ---
@app.post("/api/chat")
async def send_message(message: ChatMessage):
    """Send a message and get an AI response (Text mode - non-streaming)."""
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
    
    # Get AI response from Gemini
    try:
        session = sessions_db.get(session_id, {})
        system_prompt = session.get("system_prompt", "You are a helpful AI assistant.")
        
        model = get_gemini_model()
        
        # Build full prompt with knowledge base and chat history
        full_prompt = build_full_prompt(session_id, message.content, system_prompt)
        response = model.generate_content(full_prompt)
        ai_response = response.text
    except Exception as e:
        print(f"Gemini error: {e}")
        ai_response = "I apologize, but I'm having trouble processing your request. Please try again."
    
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
    
    # Save to disk
    save_sessions()
    save_messages()
    
    return {"user_message": user_msg, "ai_message": ai_msg}


# --- Voice Call Streaming Endpoint ---
@app.post("/api/call/stream")
async def stream_voice_call(message: CallMessage):
    """
    Voice call endpoint with streaming response.
    Returns SSE stream with text and audio chunks for lowest latency.
    Now also saves conversation to chat history and uses knowledge base.
    """
    session_id = message.session_id
    session = sessions_db.get(session_id, {})
    system_prompt = session.get("system_prompt", "You are a helpful AI assistant. Keep responses very brief.")
    voice_name = session.get("voice", "test_voice")
    
    # Initialize messages list for this session if needed
    if session_id not in messages_db:
        messages_db[session_id] = []
    
    # Save user message to chat history FIRST (before generating response)
    timestamp = datetime.now().strftime("%I:%M %p")
    user_msg = {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "user",
        "content": message.content,
        "timestamp": timestamp,
        "source": "voice"  # Mark as voice message
    }
    messages_db[session_id].append(user_msg)
    save_messages()
    
    async def generate_stream():
        try:
            # Step 1: Build full prompt with knowledge base and chat history
            model = get_gemini_model()
            # Use the same prompt builder, but add "Keep responses brief" for voice
            voice_system_prompt = system_prompt + " Keep your responses concise and natural for spoken conversation."
            full_prompt = build_full_prompt(session_id, message.content, voice_system_prompt)
            
            # Use streaming for text
            response = model.generate_content(full_prompt, stream=True)
            full_text = ""
            
            # Send text chunks as they arrive
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk.text})}\n\n"
            
            # Step 2: Save AI response to chat history
            ai_msg = {
                "id": f"msg-{uuid.uuid4().hex[:8]}",
                "role": "assistant",
                "content": full_text,
                "timestamp": datetime.now().strftime("%I:%M %p"),
                "source": "voice"  # Mark as voice message
            }
            messages_db[session_id].append(ai_msg)
            
            # Update session preview
            if session_id in sessions_db:
                sessions_db[session_id]["preview"] = message.content[:30] + "..."
            
            save_sessions()
            save_messages()
            
            # Step 3: Generate voice from complete text using WaveSpeed
            yield f"data: {json.dumps({'type': 'status', 'content': 'generating_voice'})}\n\n"
            
            # Check if WaveSpeed is configured and session has a voice
            api_key = settings_db.get("wavespeed_api_key")
            wavespeed_voice_id = session.get("wavespeed_voice_id")
            
            if api_key and wavespeed_voice_id:
                try:
                    # Use WaveSpeed for TTS with cloned voice (streaming)
                    ws = WaveSpeedManager(api_key=api_key)
                    chunk_index = 0
                    for audio_chunk in ws.speak_stream(full_text, wavespeed_voice_id):
                        audio_b64 = base64.b64encode(audio_chunk).decode('utf-8')
                        yield f"data: {json.dumps({'type': 'audio', 'index': chunk_index, 'content': audio_b64})}\n\n"
                        chunk_index += 1
                        
                    # Update last_used_at to extend expiration
                    session["voice_last_used_at"] = datetime.now().isoformat()
                    save_sessions()
                except Exception as voice_err:
                    print(f"WaveSpeed voice error: {voice_err}")
                    yield f"data: {json.dumps({'type': 'status', 'content': 'voice_error'})}\n\n"
            else:
                # No cloned voice or API key configured, skip audio
                yield f"data: {json.dumps({'type': 'status', 'content': 'no_voice_configured'})}\n\n"
            
            # Done
            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text})}\n\n"
            
        except Exception as e:
            print(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/messages/{session_id}")
async def get_messages(session_id: str):
    """Get all messages for a session."""
    return {"messages": messages_db.get(session_id, [])}


# --- Session Endpoints ---
@app.get("/api/sessions")
async def get_sessions():
    """Get all chat sessions with voice status."""
    sessions = []
    now = datetime.now()
    for s in sessions_db.values():
        # Calculate voice expiration
        voice_status = "none"
        days_until_expiry = None
        if s.get("wavespeed_voice_id"):
            last_used = s.get("voice_last_used_at") or s.get("voice_created_at")
            if last_used:
                try:
                    last_used_dt = datetime.fromisoformat(last_used)
                    days_elapsed = (now - last_used_dt).days
                    days_until_expiry = max(0, 7 - days_elapsed)
                    if days_until_expiry <= 0:
                        voice_status = "expired"
                    elif days_until_expiry <= 2:
                        voice_status = "warning"
                    else:
                        voice_status = "active"
                except:
                    voice_status = "active"
        
        sessions.append({
            "id": s["id"],
            "name": s["name"],
            "preview": s["preview"],
            "voice_status": voice_status,
            "days_until_expiry": days_until_expiry
        })
    return {"sessions": sessions}


@app.post("/api/sessions")
async def create_session(session: SessionCreate):
    """Create a new chat session (New Null)."""
    session_id = str(uuid.uuid4().hex[:8])
    new_session = {
        "id": session_id,
        "name": session.name,
        "preview": "New conversation started...",
        "system_prompt": f"You are {session.name}. Be helpful and engaging. Keep responses concise for voice synthesis.",
        "voice": "test_voice",
        "wavespeed_voice_id": None,
        "voice_created_at": None,
        "voice_last_used_at": None
    }
    sessions_db[session_id] = new_session
    
    # Initialize with welcome message
    messages_db[session_id] = [{
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "assistant",
        "content": f"Hello. I am now initialized as {session.name}. How may I assist you?",
        "timestamp": datetime.now().strftime("%I:%M %p")
    }]
    
    # Save to disk
    save_sessions()
    save_messages()
    
    return {"id": session_id, "name": session.name, "preview": new_session["preview"]}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del sessions_db[session_id]
    if session_id in messages_db:
        del messages_db[session_id]
    
    # Save to disk
    save_sessions()
    save_messages()
    
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


# --- AI Refresh Endpoint (SSE Streaming) ---
def sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"


class RefreshRequest(BaseModel):
    session_id: Optional[str] = None


@app.post("/api/refresh")
async def refresh_ai_memory(request: RefreshRequest = None):
    """
    Trigger AI memory reindexing and voice cloning with SSE streaming progress.
    """
    session_id = request.session_id if request else None
    
    async def generate_stream():
        try:
            # Step 1: Starting
            yield sse_event({"step": "progress", "progress": 5, "message": "Starting memory refresh..."})
            
            # Step 2: Processing text files
            text_count = len(list((UPLOAD_DIR / "text").iterdir()))
            yield sse_event({"step": "progress", "progress": 20, "message": f"Processing {text_count} text files..."})
            
            # Step 3: Processing voice files
            voice_folder = UPLOAD_DIR / "voice"
            voice_files = list(voice_folder.iterdir()) if voice_folder.exists() else []
            yield sse_event({"step": "progress", "progress": 40, "message": f"Found {len(voice_files)} voice files..."})
            
            voice_cloning_result = None
            
            # Step 4: Voice cloning if files exist
            if voice_files and session_id and session_id in sessions_db:
                api_key = settings_db.get("wavespeed_api_key")
                if api_key:
                    session = sessions_db[session_id]
                    voice_file = voice_files[-1]
                    session_name = session["name"]
                    
                    yield sse_event({"step": "progress", "progress": 50, "message": f"Cloning voice for {session_name}..."})
                    
                    try:
                        # Generate voice ID
                        clean_session_id = session_id.replace('-', '')
                        clean_name = ''.join(c for c in session_name if c.isalnum())
                        voice_name = f"NullTale{clean_session_id}{clean_name}"
                        
                        yield sse_event({"step": "progress", "progress": 60, "message": "Uploading to WaveSpeed..."})
                        
                        # Clone via WaveSpeed
                        ws = WaveSpeedManager(api_key=api_key)
                        voice_id = ws.clone_voice(voice_name, str(voice_file))
                        
                        yield sse_event({"step": "progress", "progress": 85, "message": "Voice cloned successfully!"})
                        
                        # Update session
                        now = datetime.now().isoformat()
                        session["wavespeed_voice_id"] = voice_id
                        session["voice_created_at"] = now
                        session["voice_last_used_at"] = now
                        save_sessions()
                        
                        voice_cloning_result = {"success": True, "voice_id": voice_id, "message": f"Voice cloned for {session_name}"}
                        
                        # Clean up
                        voice_file.unlink()
                        
                    except Exception as e:
                        error_msg = str(e)
                        yield sse_event({"step": "progress", "progress": 85, "message": f"Voice cloning failed: {error_msg}"})
                        voice_cloning_result = {"success": False, "error": error_msg}
                else:
                    yield sse_event({"step": "progress", "progress": 85, "message": "WaveSpeed API key not configured"})
                    voice_cloning_result = {"success": False, "error": "WaveSpeed API key not configured"}
            else:
                yield sse_event({"step": "progress", "progress": 85, "message": "No voice files to process"})
            
            # Step 5: Complete
            yield sse_event({"step": "complete", "progress": 100, "message": "Memory refresh complete!", "voice_cloning": voice_cloning_result})
            
        except Exception as e:
            yield sse_event({"step": "error", "message": str(e)})
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/refresh/ready")
async def check_refresh_ready():
    """Check if AI refresh is ready (files uploaded with subjects selected)."""
    text_files = list((UPLOAD_DIR / "text").iterdir())
    voice_files = list((UPLOAD_DIR / "voice").iterdir())
    
    if len(text_files) == 0 and len(voice_files) == 0:
        return {"ready": False, "reason": "Upload some files first"}
    
    return {"ready": True, "reason": "Ready to refresh"}


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
    if settings.wavespeed_api_key is not None:
        settings_db["wavespeed_api_key"] = settings.wavespeed_api_key
    
    # Save to disk
    save_settings()
    
    return {"success": True, "settings": settings_db}


@app.get("/api/settings/wavespeed-key")
async def get_wavespeed_key_status():
    """Check if WaveSpeed API key is configured (doesn't return the actual key)."""
    has_key = bool(settings_db.get("wavespeed_api_key"))
    return {
        "configured": has_key,
        "message": "API key is configured" if has_key else "No API key set"
    }


@app.post("/api/settings/wavespeed-key")
async def set_wavespeed_key(data: dict):
    """Save WaveSpeed API key."""
    api_key = data.get("api_key", "").strip()
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    
    if len(api_key) < 20:
        raise HTTPException(status_code=400, detail="Invalid API key format")
    
    settings_db["wavespeed_api_key"] = api_key
    save_settings()
    
    return {"success": True, "message": "API key saved successfully"}


@app.delete("/api/settings/wavespeed-key")
async def delete_wavespeed_key():
    """Delete the stored WaveSpeed API key."""
    if settings_db.get("wavespeed_api_key"):
        settings_db["wavespeed_api_key"] = ""
        save_settings()
        return {"success": True, "message": "API key removed"}
    raise HTTPException(status_code=404, detail="No API key to remove")


@app.post("/api/settings/wavespeed-key/test")
async def test_wavespeed_key():
    """Test if the saved WaveSpeed API key is valid."""
    api_key = settings_db.get("wavespeed_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")
    
    try:
        ws = WaveSpeedManager(api_key=api_key)
        voices = ws.list_voices()
        return {"success": True, "message": "API key is valid!", "voices": voices}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API key test failed: {str(e)}")


# --- Voice Management ---
@app.get("/api/voices")
async def list_voices():
    """List available WaveSpeed voice profiles."""
    wavespeed_voices = WaveSpeedManager.SYSTEM_VOICES if settings_db.get("wavespeed_api_key") else []
    return {
        "wavespeed_voices": wavespeed_voices
    }


@app.post("/api/voice/clone/{session_id}")
async def clone_voice_for_session(session_id: str, file: UploadFile = File(...)):
    """
    Clone a voice from uploaded audio and link it to a session.
    Audio should be 10s-5min, MP3/WAV/M4A format.
    """
    # Check session exists
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check API key is set
    api_key = settings_db.get("wavespeed_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="WaveSpeed API key not configured. Please set it in Settings.")
    
    # Save uploaded file temporarily
    temp_path = UPLOAD_DIR / "voice" / f"temp_{uuid.uuid4().hex}{Path(file.filename).suffix}"
    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # Generate voice ID - alphanumeric only, no hyphens (WaveSpeed requirement)
        session = sessions_db[session_id]
        # Remove hyphens from session_id and sanitize name
        clean_session_id = session_id.replace('-', '')
        clean_name = ''.join(c for c in session['name'] if c.isalnum())
        voice_name = f"NullTale{clean_session_id}{clean_name}"
        
        # Clone via WaveSpeed
        ws = WaveSpeedManager(api_key=api_key)
        voice_id = ws.clone_voice(voice_name, str(temp_path))
        
        # Update session with voice info
        now = datetime.now().isoformat()
        session["wavespeed_voice_id"] = voice_id
        session["voice_created_at"] = now
        session["voice_last_used_at"] = now
        
        # Save to disk
        save_sessions()
        
        return {
            "success": True,
            "voice_id": voice_id,
            "session_id": session_id,
            "expires_in_days": 7,
            "message": f"Voice cloned successfully for {session['name']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {str(e)}")
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@app.get("/api/voice/status/{session_id}")
async def get_voice_status(session_id: str):
    """Get voice status and expiration info for a session."""
    if session_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions_db[session_id]
    voice_id = session.get("wavespeed_voice_id")
    
    if not voice_id:
        return {
            "has_voice": False,
            "voice_status": "none",
            "message": "No voice configured for this personality"
        }
    
    # Calculate expiration
    last_used = session.get("voice_last_used_at") or session.get("voice_created_at")
    if last_used:
        try:
            last_used_dt = datetime.fromisoformat(last_used)
            days_elapsed = (datetime.now() - last_used_dt).days
            days_remaining = max(0, 7 - days_elapsed)
            
            if days_remaining <= 0:
                status = "expired"
                message = "Voice expired. Please re-upload to continue using."
            elif days_remaining <= 2:
                status = "warning"
                message = f"Voice expires in {days_remaining} day(s). Use it or re-upload to extend."
            else:
                status = "active"
                message = f"Voice active. Expires in {days_remaining} days."
            
            return {
                "has_voice": True,
                "voice_id": voice_id,
                "voice_status": status,
                "days_remaining": days_remaining,
                "message": message
            }
        except:
            pass
    
    return {
        "has_voice": True,
        "voice_id": voice_id,
        "voice_status": "active",
        "message": "Voice is active"
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting NullTale Backend on http://localhost:5000")
    print("Gemini Model: gemini-2.5-flash-lite")
    print("Voice: WaveSpeed Cloud TTS")
    uvicorn.run(app, host="0.0.0.0", port=5000)
