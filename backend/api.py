"""
NullTale Backend API - Consolidated Server
Combines file processing (originally Flask) and Chat/Voice features (originally FastAPI).
"""

import os
import sys
import uuid
import json
import hashlib
import time
import base64
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union

from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# --- Google Gemini Integration ---
import google.generativeai as genai

# Load .env from root Nulltale folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)

# --- Import processing modules ---
from processor import classify_file, extract_participants, generate_style_file, generate_context_chunks
from instagram_zip_processor import (
    extract_zip, find_conversations, merge_conversation_messages, cleanup_zip
)
from discord_zip_processor import (
    extract_zip as discord_extract_zip,
    find_dm_conversations as discord_find_conversations,
    convert_discord_to_instagram_format,
    cleanup_zip as discord_cleanup_zip
)
from style_summarizer import generate_style_summary
from context_embedder import generate_embeddings
from chatbot import PersonaChatbot

# --- Voice/TTS imports ---
from wavespeed_manager import WaveSpeedManager
from secrets_manager import (
    get_wavespeed_key, save_wavespeed_key, has_wavespeed_key, delete_secret
)

app = Flask(__name__)

# CORS for Vite dev server
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

# --- Configuration & Directories ---
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "text").mkdir(exist_ok=True)
(UPLOAD_DIR / "voice").mkdir(exist_ok=True)

PREPROCESSED_DIR = Path(__file__).parent / "preprocessed"
PREPROCESSED_DIR.mkdir(exist_ok=True)

CHATS_DIR = Path(__file__).parent / "chats"
CHATS_DIR.mkdir(exist_ok=True)

ALLOWED_TEXT_EXTENSIONS = {'.txt', '.json', '.zip', '.html'}

# --- Global State ---
settings_db = {
    "model_version": "v2.5",
    "temperature": 0.7
}
# Lazy-loaded Gemini model
_gemini_model = None
# Lazy-loaded WaveSpeed manager
_wavespeed_manager = None

# In-memory storage (backed by file persistence)
sessions_db = {}
messages_db = {}
chatbots = {}         # Active chatbot instances: session_id -> PersonaChatbot
pending_zips = {}     # zip_id -> extraction info

# --- Helper Functions ---

def get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel("gemini-2.5-flash-lite")
    return _gemini_model

def get_wavespeed_manager(force_reload: bool = False):
    global _wavespeed_manager
    if _wavespeed_manager is None or force_reload:
        api_key = get_wavespeed_key()
        if not api_key:
            return None
        _wavespeed_manager = WaveSpeedManager(api_key=api_key)
    return _wavespeed_manager

def save_sessions():
    """Save sessions metadata to disk."""
    sessions_file = CHATS_DIR / "sessions.json"
    try:
        with open(sessions_file, "w", encoding="utf-8") as f:
            json.dump(sessions_db, f, indent=2)
    except Exception as e:
        print(f"Failed to save sessions: {e}")

def save_message_history(session_id):
    """Save message history for a session."""
    if session_id not in messages_db:
        return
    history_file = CHATS_DIR / f"history_{session_id}.json"
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(messages_db[session_id], f, indent=2)
    except Exception as e:
        print(f"Failed to save history for {session_id}: {e}")

def load_persistence():
    """Load sessions and histories from disk."""
    global sessions_db, messages_db
    
    # Load sessions
    sessions_file = CHATS_DIR / "sessions.json"
    if sessions_file.exists():
        try:
            with open(sessions_file, "r", encoding="utf-8") as f:
                sessions_db.update(json.load(f))
        except Exception as e:
            print(f"Failed to load sessions: {e}")
            
    # Load histories
    for session_id in sessions_db:
        history_file = CHATS_DIR / f"history_{session_id}.json"
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    messages_db[session_id] = json.load(f)
            except Exception as e:
                print(f"Failed to load history for {session_id}: {e}")
                messages_db[session_id] = []
        else:
            messages_db[session_id] = []

def get_available_subjects():
    """List available subjects based on preprocessed files."""
    subjects = []
    if PREPROCESSED_DIR.exists():
        for file_path in PREPROCESSED_DIR.iterdir():
            if file_path.name.endswith('_embeddings.json'):
                subject = file_path.stem.replace('_embeddings', '')
                subjects.append(subject)
    return subjects

def get_or_create_chatbot(session_id: str):
    """Get existing chatbot or create new one for session."""
    if session_id in chatbots:
        return chatbots[session_id]
        
    if session_id not in sessions_db:
        return None
        
    subject = sessions_db[session_id].get("subject")
    if not subject:
        return None
        
    summary_path = PREPROCESSED_DIR / f"{subject}_style_summary.txt"
    embeddings_path = PREPROCESSED_DIR / f"{subject}_embeddings.json"
    
    if not summary_path.exists() or not embeddings_path.exists():
        return None
        
    try:
        # Pass Gemini model to chatbot
        model = get_gemini_model()
        chatbot = PersonaChatbot(
            str(summary_path),
            str(embeddings_path),
            model=model
        )
        chatbots[session_id] = chatbot
        return chatbot
    except Exception as e:
        print(f"Failed to create chatbot for {subject}: {e}")
        return None

# --- File Processing Helpers ---

def compute_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def extract_message_fingerprints(file_path, n=20):
    fingerprints = set()
    try:
        detected_type = classify_file(str(file_path))
        if detected_type == 'Instagram':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            messages = data.get('messages', [])
            boundary = messages[:n] + messages[-n:]
            for msg in boundary:
                sender = msg.get('sender_name', '')
                content = msg.get('content', '')
                if content:
                    fp = hashlib.md5(f"{sender}:{content}".encode()).hexdigest()[:12]
                    fingerprints.add(fp)
        elif detected_type == 'WhatsApp':
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            import re
            msg_pattern = r'^\d{1,2}/\d{1,2}/\d{2,4},\s\d{1,2}:\d{2}.*-\s(.*?):\s(.*)$'
            msg_lines = []
            for line in lines:
                match = re.match(msg_pattern, line, re.IGNORECASE)
                if match:
                    msg_lines.append((match.group(1), match.group(2)))
            boundary = msg_lines[:n] + msg_lines[-n:]
            for sender, content in boundary:
                if content:
                    fp = hashlib.md5(f"{sender}:{content}".encode()).hexdigest()[:12]
                    fingerprints.add(fp)
    except Exception:
        pass
    return fingerprints

def get_existing_fingerprints(folder):
    file_fingerprints = {}
    if not folder.exists():
        return file_fingerprints
    for file_path in folder.iterdir():
        if file_path.is_file() and not file_path.name.endswith('.meta.json'):
            try:
                fps = extract_message_fingerprints(file_path)
                if fps:
                    file_fingerprints[file_path.name] = fps
            except Exception:
                pass
    return file_fingerprints

def check_content_overlap(new_fingerprints, existing_fingerprints, threshold=0.8):
    if not new_fingerprints:
        return False, None
    for filename, existing_fps in existing_fingerprints.items():
        if not existing_fps:
            continue
        overlap = len(new_fingerprints & existing_fps)
        min_size = min(len(new_fingerprints), len(existing_fps))
        if min_size > 0 and overlap / min_size >= threshold:
            return True, filename
    return False, None

def get_file_metadata(file_path):
    path = Path(file_path)
    file_id = path.stem
    detected_type = classify_file(str(path))
    participants = []
    if detected_type in ["WhatsApp", "Instagram", "InstagramHTML", "LINE"]:
        participants = extract_participants(str(path), detected_type)
    
    return {
        "id": file_id,
        "original_name": path.name,
        "saved_as": path.name,
        "file_type": "text" if path.parent.name == "text" else "voice",
        "detected_type": detected_type,
        "participants": participants,
        "subject": None,
        "path": str(path),
        "size": path.stat().st_size
    }

def scan_uploads_folder(file_type):
    folder = UPLOAD_DIR / file_type
    if not folder.exists(): 
        return []
    
    files = []
    for file_path in folder.iterdir():
        if not file_path.is_file() or file_path.name.endswith('.meta.json'):
            continue
        try:
            metadata = get_file_metadata(file_path)
            # Load overrides
            meta_file = folder / f"{metadata['id']}.meta.json"
            if meta_file.exists():
                with open(meta_file, 'r') as f:
                    meta_data = json.load(f)
                    metadata['subject'] = meta_data.get('subject')
                    if 'detected_type' in meta_data:
                        metadata['detected_type'] = meta_data['detected_type']
                    if 'participants' in meta_data:
                        metadata['participants'] = meta_data['participants']
            files.append(metadata)
        except Exception as e:
            print(f"Error scanning file {file_path}: {e}")
    return files

# --- API Endpoints: Files ---

@app.route("/api/files/<file_type>", methods=["POST"])
def upload_files(file_type):
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid file type"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400
        
    folder = UPLOAD_DIR / file_type
    existing_fingerprints = get_existing_fingerprints(folder)
    batch_fingerprints = {}
    
    uploaded = []
    rejected = []
    
    for file in files:
        if file.filename == "": continue
        
        original_name = secure_filename(file.filename)
        file_ext = Path(original_name).suffix.lower()
        
        # Validation
        if file_type == "text" and file_ext not in ALLOWED_TEXT_EXTENSIONS:
            rejected.append({"name": file.filename, "reason": "Invalid extension"})
            continue
            
        file_id = uuid.uuid4().hex[:12]
        unique_name = f"{file_id}{file_ext}"
        file_path = folder / unique_name
        
        file.save(str(file_path))
        
        # Content overlap check for text files
        if file_type == "text" and file_ext != '.zip':
            new_fingerprints = extract_message_fingerprints(file_path)
            is_dup, match = check_content_overlap(new_fingerprints, existing_fingerprints)
            if is_dup:
                file_path.unlink()
                rejected.append({"name": file.filename, "reason": f"Duplicate of {match}"})
                continue
            
            is_dup_batch, match_batch = check_content_overlap(new_fingerprints, batch_fingerprints)
            if is_dup_batch:
                file_path.unlink()
                rejected.append({"name": file.filename, "reason": f"Duplicate details in batch"})
                continue
                
            if new_fingerprints:
                batch_fingerprints[file.filename] = new_fingerprints
        
        # ZIP handling
        if file_type == "text" and file_ext == '.zip':
            # Simplified for brevity - reuse logic from original api.py
            try:
                import zipfile
                zip_type = None
                with zipfile.ZipFile(str(file_path), 'r') as zf:
                    names = zf.namelist()
                    if any('messages/index.json' in n.lower() for n in names):
                        zip_type = 'discord'
                    elif any('inbox/' in n.lower() for n in names):
                        zip_type = 'instagram'
                
                if zip_type == 'discord':
                    extracted_path = discord_extract_zip(str(file_path), file_id)
                    conversations = discord_find_conversations(extracted_path)
                    pending_zips[file_id] = {
                        "zip_path": str(file_path), "extracted_path": str(extracted_path),
                        "original_name": file.filename, "conversations": conversations, "zip_type": "discord"
                    }
                    return jsonify({
                        "success": True, "type": "discord_zip_upload", "zip_id": file_id,
                        "conversations": conversations, "uploaded": [], "rejected": []
                    })
                elif zip_type == 'instagram':
                    extracted_path = extract_zip(str(file_path), file_id)
                    conversations = find_conversations(extracted_path)
                    pending_zips[file_id] = {
                        "zip_path": str(file_path), "extracted_path": str(extracted_path),
                        "original_name": file.filename, "conversations": conversations, "zip_type": "instagram"
                    }
                    return jsonify({
                        "success": True, "type": "zip_upload", "zip_id": file_id,
                        "conversations": conversations, "uploaded": [], "rejected": []
                    })
            except Exception as e:
                file_path.unlink()
                rejected.append({"name": file.filename, "reason": f"ZIP error: {str(e)}"})
                continue

        # Standard file processing
        try:
            detected_type = classify_file(str(file_path)) if file_type == "text" else "voice"
            participants = extract_participants(str(file_path), detected_type) if file_type == "text" else []
            
            uploaded.append({
                "id": file_id, "original_name": file.filename, "saved_as": unique_name,
                "file_type": file_type, "detected_type": detected_type, "participants": participants,
                "subject": None, "path": str(file_path), "size": file_path.stat().st_size
            })
        except Exception:
            # Fallback
            uploaded.append({"id": file_id, "file_type": file_type, "saved_as": unique_name})

    return jsonify({
        "success": True, "uploaded": uploaded, "rejected": rejected,
        "uploaded_count": len(uploaded)
    })

@app.route("/api/files/text/zip/select", methods=["POST"])
def select_zip_conversations():
    data = request.get_json()
    zip_id = data.get("zip_id")
    selected_folders = data.get("conversations", [])
    
    if not zip_id or zip_id not in pending_zips:
        return jsonify({"error": "ZIP not found"}), 404
        
    zip_info = pending_zips[zip_id]
    conversations = zip_info["conversations"]
    zip_type = zip_info.get("zip_type", "instagram")
    
    selected_convs = [c for c in conversations if c["folder_name"] in selected_folders]
    uploaded = []
    rejected = []
    folder = UPLOAD_DIR / "text"
    
    for conv in selected_convs:
        try:
            if zip_type == "discord":
                merged_data = convert_discord_to_instagram_format(conv["path"])
                source_label = "Discord"
            else:
                merged_data = merge_conversation_messages(conv["path"])
                source_label = "Instagram"
                
            if not merged_data:
                rejected.append({"name": conv["display_name"], "reason": "Failed to merge"})
                continue
                
            file_id = uuid.uuid4().hex[:12]
            file_name = f"{file_id}.json"
            file_path = folder / file_name
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False)
                
            detected_type = "Discord" if zip_type == "discord" else "Instagram"
            
            # Save meta
            meta_path = folder / f"{file_id}.meta.json"
            with open(meta_path, 'w') as f:
                json.dump({
                    "detected_type": detected_type,
                    "participants": [p.get('name') for p in merged_data.get('participants', [])],
                    "original_name": conv['display_name']
                }, f)
                
            uploaded.append({
                "id": file_id, "original_name": f"{conv['display_name']} ({source_label})",
                "detected_type": detected_type
            })
            
        except Exception as e:
            rejected.append({"name": conv["display_name"], "reason": str(e)})

    # Cleanup
    try:
        Path(zip_info["zip_path"]).unlink(missing_ok=True)
        if zip_type == "discord":
            discord_cleanup_zip(zip_id)
        else:
            cleanup_zip(zip_id)
    except: pass
    del pending_zips[zip_id]
    
    return jsonify({"success": True, "uploaded": uploaded, "rejected": rejected})

@app.route("/api/files/<file_type>", methods=["GET"])
def list_files(file_type):
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid type"}), 400
    files = scan_uploads_folder(file_type)
    return jsonify({"files": files, "count": len(files)})

@app.route("/api/files/<file_type>/<file_id>/subject", methods=["POST"])
def set_subject(file_type, file_id):
    folder = UPLOAD_DIR / file_type
    matches = list(folder.glob(f"{file_id}.*"))
    if not matches: return jsonify({"error": "Not found"}), 404
    
    subject = request.json.get("subject")
    if not subject: return jsonify({"error": "No subject"}), 400
    
    meta_file = folder / f"{file_id}.meta.json"
    meta_data = {}
    if meta_file.exists():
        with open(meta_file, 'r') as f: meta_data = json.load(f)
    meta_data["subject"] = subject
    with open(meta_file, 'w') as f: json.dump(meta_data, f)
    
    return jsonify({"success": True, "subject": subject})

@app.route("/api/files/<file_type>/<file_id>", methods=["DELETE"])
def delete_file(file_type, file_id):
    folder = UPLOAD_DIR / file_type
    matches = list(folder.glob(f"{file_id}.*"))
    deleted = False
    for p in matches:
        p.unlink()
        deleted = True
    (folder / f"{file_id}.meta.json").unlink(missing_ok=True)
    
    if not deleted: return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# --- API Endpoints: Processing & Refresh ---

@app.route("/api/refresh/ready", methods=["GET"])
def check_refresh_ready():
    files = scan_uploads_folder("text")
    if not files:
        return jsonify({"ready": False, "reason": "No files uploaded"})
    files_with_subject = [f for f in files if f.get("subject")]
    if len(files_with_subject) < len(files):
        return jsonify({"ready": False, "reason": "Missing subjects"})
    return jsonify({"ready": True})

@app.route("/api/refresh", methods=["POST"])
def refresh_memory():
    session_id = request.json.get("session_id")
    
    def generate():
        try:
            yield f"data: {json.dumps({'step': 'starting', 'progress': 0, 'message': 'Starting refresh...'})}\n\n"
            
            # 1. Text Processing
            files = scan_uploads_folder("text")
            subject_files = {}
            for f in files:
                sub = f["subject"]
                if sub not in subject_files: subject_files[sub] = []
                subject_files[sub].append(f)
            
            yield f"data: {json.dumps({'step': 'cleaning', 'progress': 10, 'message': 'Cleaning old data...'})}\n\n"
            for p in PREPROCESSED_DIR.glob("*"): p.unlink()
            
            total = len(subject_files)
            for idx, (subject, s_files) in enumerate(subject_files.items()):
                yield f"data: {json.dumps({'step': 'processing', 'progress': 20, 'message': f'Processing {subject}...'})}\n\n"
                
                results = [(f["original_name"], f["path"], f["detected_type"], subject) for f in s_files]
                
                # Style Generation
                temp_style = PREPROCESSED_DIR / f"{subject}_style_temp.txt"
                generate_style_file(results, str(temp_style))
                
                # Context Chunks
                chunks_path = PREPROCESSED_DIR / f"{subject}_context_chunks.json"
                generate_context_chunks(results, str(chunks_path))
                
                # Style Summary
                yield f"data: {json.dumps({'step': 'summary', 'progress': 50, 'message': f'Analyzing style for {subject}...'})}\n\n"
                summary_path = PREPROCESSED_DIR / f"{subject}_style_summary.txt"
                generate_style_summary(str(temp_style), str(summary_path), subject)
                
                # Embeddings
                yield f"data: {json.dumps({'step': 'embeddings', 'progress': 70, 'message': f'Generating embeddings for {subject}...'})}\n\n"
                embeddings_path = PREPROCESSED_DIR / f"{subject}_embeddings.json"
                generate_embeddings(str(chunks_path), str(embeddings_path))
                
                if temp_style.exists(): temp_style.unlink()
            
            # 2. Voice Cloning (if session provided)
            voice_result = None
            if session_id and session_id in sessions_db:
                # Check for staged voice files
                voice_files = scan_uploads_folder("voice")
                # Sort by newest
                voice_files.sort(key=lambda x: os.path.getmtime(x["path"]), reverse=True)
                
                api_key = get_wavespeed_key()
                
                if voice_files and api_key and _wavespeed_manager:
                    yield f"data: {json.dumps({'step': 'voice', 'progress': 80, 'message': 'Cloning voice...'})}\n\n"
                    target_file = voice_files[0]
                    session = sessions_db[session_id]
                    
                    try:
                        # Construct valid voice name
                        clean_name = "".join(c for c in session["name"] if c.isalnum())
                        voice_name_id = f"NullTale{session_id}{clean_name}"
                        
                        manager = get_wavespeed_manager()
                        voice_id = manager.clone_voice(voice_name_id, target_file["path"])
                        
                        # Update session
                        now = datetime.now().isoformat()
                        session["wavespeed_voice_id"] = voice_id
                        session["voice_created_at"] = now
                        session["voice_last_used_at"] = now
                        save_sessions()
                        
                        # Cleanup used voice file
                        Path(target_file["path"]).unlink()
                        
                        voice_result = {"success": True, "message": "Voice cloned successfully"}
                    except Exception as e:
                        voice_result = {"error": str(e)}
            
            yield f"data: {json.dumps({'step': 'complete', 'progress': 100, 'message': 'Refresh complete!', 'voice_cloning': voice_result})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# --- API Endpoints: Sessions & Chat ---

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    return jsonify({"sessions": list(sessions_db.values())})

@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.json or {}
    subjects = get_available_subjects()
    session_id = uuid.uuid4().hex[:8]
    subject = subjects[0] if subjects else None
    
    session = {
        "id": session_id,
        "name": data.get("name", "New Chat"),
        "subject": subject,
        "preview": "Start chatting...",
        "created_at": datetime.now().isoformat()
    }
    sessions_db[session_id] = session
    messages_db[session_id] = []
    
    if subject:
        get_or_create_chatbot(session_id)
        
    save_sessions()
    return jsonify(session)

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    if session_id in sessions_db: del sessions_db[session_id]
    if session_id in messages_db: del messages_db[session_id]
    if session_id in chatbots: del chatbots[session_id]
    
    # Delete persistence files
    (CHATS_DIR / f"{session_id}.json").unlink(missing_ok=True) # Old format
    (CHATS_DIR / f"history_{session_id}.json").unlink(missing_ok=True)
    save_sessions()
    
    return jsonify({"success": True})

@app.route("/api/messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    return jsonify({"messages": messages_db.get(session_id, [])})

@app.route("/api/chat", methods=["POST"])
def send_message():
    data = request.json
    content = data.get("content", "").strip()
    session_id = data.get("session_id")
    
    if not content or not session_id:
        return jsonify({"error": "Missing content or session_id"}), 400
        
    if session_id not in sessions_db:
        # Create implicitly
        create_session()
        
    # User message
    user_msg = {
        "id": uuid.uuid4().hex[:8],
        "role": "user",
        "content": content,
        "timestamp": datetime.now().strftime("%I:%M %p")
    }
    if session_id not in messages_db: messages_db[session_id] = []
    messages_db[session_id].append(user_msg)
    
    # Get AI response
    chatbot = get_or_create_chatbot(session_id)
    ai_content = "I'm not ready yet. Please upload files and refresh memory."
    
    if chatbot:
        try:
            ai_content = chatbot.chat(content)
        except Exception as e:
            ai_content = f"Error: {e}"
            
    # Process AI response (split into messages)
    import re
    parts = [p.strip() for p in re.split(r'\n{2,}', ai_content) if p.strip()]
    if not parts: parts = [ai_content]
    
    ai_messages = []
    ts = datetime.now().strftime("%I:%M %p")
    
    for part in parts:
        msg = {
            "id": uuid.uuid4().hex[:8],
            "role": "assistant",
            "content": part,
            "timestamp": ts
        }
        messages_db[session_id].append(msg)
        ai_messages.append(msg)
        
    # Update preview
    if ai_messages:
        preview = ai_messages[0]["content"]
        sessions_db[session_id]["preview"] = preview[:50] + "..." if len(preview) > 50 else preview
        
    save_message_history(session_id)
    save_sessions()
    
    return jsonify({
        "user_message": user_msg,
        "ai_message": ai_messages[0],
        "ai_messages": ai_messages
    })


# --- API Endpoints: Voice Cloning & Calls ---

@app.route("/api/voice/status/<session_id>", methods=["GET"])
def get_voice_status(session_id):
    if session_id not in sessions_db:
        return jsonify({"error": "Session not found"}), 404
        
    session = sessions_db[session_id]
    voice_id = session.get("wavespeed_voice_id")
    
    if not voice_id:
        return jsonify({"has_voice": False, "voice_status": "none", "message": "No voice configured"})
        
    # Check expiration
    last_used = session.get("voice_last_used_at") or session.get("voice_created_at")
    status = "active"
    days_left = 7
    message = "Voice active"
    
    if last_used:
        try:
            last_dt = datetime.fromisoformat(last_used)
            elapsed = (datetime.now() - last_dt).days
            days_left = max(0, 7 - elapsed)
            
            if days_left <= 0:
                status = "expired"
                message = "Voice expired. Please re-upload."
            elif days_left <= 2:
                status = "warning"
                message = f"Expiring in {days_left} days."
        except: pass
        
    return jsonify({
        "has_voice": True, "voice_id": voice_id,
        "voice_status": status, "days_remaining": days_left, "message": message
    })

@app.route("/api/voice/clone/<session_id>", methods=["POST"])
def clone_voice_endpoint(session_id):
    """Direct cloning endpoint."""
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
        
    file = request.files["file"]
    manager = get_wavespeed_manager()
    if not manager:
        return jsonify({"error": "WaveSpeed key not set"}), 400
        
    temp_path = UPLOAD_DIR / "voice" / f"temp_{uuid.uuid4().hex}.wav"
    file.save(str(temp_path))
    
    try:
        session = sessions_db.get(session_id, {"name": "Unknown"})
        clean_name = "".join(c for c in session["name"] if c.isalnum())
        voice_id = manager.clone_voice(f"NullTale{session_id[:6]}{clean_name}", str(temp_path))
        
        if session_id in sessions_db:
            sessions_db[session_id]["wavespeed_voice_id"] = voice_id
            save_sessions()
            
        return jsonify({"success": True, "voice_id": voice_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if temp_path.exists(): temp_path.unlink()

@app.route("/api/call/stream", methods=["POST"])
def stream_call():
    """Stream voice call response (text + audio)."""
    data = request.json
    content = data.get("content")
    session_id = data.get("session_id")
    
    if not content or not session_id:
        return jsonify({"error": "Missing params"}), 400
        
    def generate():
        # 1. Get AI Text Response
        # Note: Ideally we'd stream text from Gemini too, but for now we get full block
        chatbot = get_or_create_chatbot(session_id)
        if not chatbot:
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI not ready'})}\n\n"
            return
            
        text_response = chatbot.chat(content)
        
        # Send text event
        yield f"data: {json.dumps({'type': 'text', 'content': text_response})}\n\n"
        
        # 2. Get Voice Audio
        session = sessions_db.get(session_id)
        voice_id = session.get("wavespeed_voice_id")
        manager = get_wavespeed_manager()
        
        if voice_id and manager:
            yield f"data: {json.dumps({'type': 'status', 'content': 'speaking'})}\n\n"
            try:
                # Update usage time
                if session_id in sessions_db:
                    sessions_db[session_id]["voice_last_used_at"] = datetime.now().isoformat()
                    save_sessions()
                    
                idx = 0
                for chunk in manager.speak_stream(text_response, voice_id):
                    b64 = base64.b64encode(chunk).decode('utf-8')
                    yield f"data: {json.dumps({'type': 'audio', 'index': idx, 'content': b64})}\n\n"
                    idx += 1
            except Exception as e:
                print(f"Voice generation error: {e}")
                # Don't fail the whole request, text was already sent
                
        yield f"data: {json.dumps({'type': 'done', 'full_text': text_response})}\n\n"
        
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route("/api/voices", methods=["GET"])
def list_voices():
    manager = get_wavespeed_manager()
    if not manager:
        return jsonify({"system": [], "cloned": [], "message": "API key not set"})
    return jsonify(manager.list_voices())

# --- API Endpoints: Settings ---

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(settings_db)

@app.route("/api/settings", methods=["PUT"])
def update_settings():
    data = request.json
    settings_db.update(data)
    return jsonify({"success": True, "settings": settings_db})

@app.route("/api/settings/wavespeed-key", methods=["GET", "POST", "DELETE"])
def wavespeed_key_mgmt():
    if request.method == "GET":
        has_key = has_wavespeed_key()
        return jsonify({"configured": has_key})
        
    if request.method == "POST":
        key = request.json.get("api_key")
        if save_wavespeed_key(key):
            get_wavespeed_manager(force_reload=True)
            return jsonify({"success": True})
        return jsonify({"error": "Failed to save"}), 500
        
    if request.method == "DELETE":
        delete_secret("wavespeed_api_key")
        global _wavespeed_manager
        _wavespeed_manager = None
        return jsonify({"success": True})

@app.route("/api/settings/wavespeed-key/test", methods=["POST"])
def test_wavespeed_key():
    try:
        mgr = get_wavespeed_manager(force_reload=True)
        if mgr:
            return jsonify({"success": True, "voices": mgr.list_voices()})
        return jsonify({"success": False, "error": "No key"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/warmup", methods=["POST"])
def warmup():
    # Preload models
    get_gemini_model()
    get_wavespeed_manager()
    return jsonify({"success": True})

# --- Main Entry Point ---

if __name__ == "__main__":
    load_persistence()
    print("Starting NullTale API (Consolidated) on http://localhost:5000")
    print(f"Data directory: {UPLOAD_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
