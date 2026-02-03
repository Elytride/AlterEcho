"""
NullTale Backend API - Per-Chat Architecture
Combines file processing and Chat/Voice features into session-specific isolation.
"""

import os
import sys
import uuid
import json
import hashlib
import time
import base64
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union

from flask import Flask, request, jsonify, Response, stream_with_context, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# --- Google Gemini Integration ---
from google import genai
from google.genai import types

# Load .env from root Nulltale folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini
# In the new SDK, we instantiate a client. We'll do this in get_gemini_model/client.
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Import processing modules ---
from processor import classify_file, extract_participants, generate_style_file, generate_context_chunks, generate_context_file
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
from wavespeed_manager import WaveSpeedManager
from secrets_manager import (
    get_wavespeed_key, save_wavespeed_key, has_wavespeed_key, delete_secret,
    get_gemini_key, save_gemini_key, has_gemini_key
)

app = Flask(__name__)

# CORS for Vite dev server
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

# --- Configuration & Directories ---
CHATS_DIR = Path(__file__).parent / "data" / "chats"
CHATS_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = Path(__file__).parent / "data" / "user_settings.json"

ALLOWED_TEXT_EXTENSIONS = {'.txt', '.json', '.zip', '.html'}

# --- Global State ---
# Lazy-loaded Gemini model
_gemini_model = None
# Lazy-loaded WaveSpeed manager
_wavespeed_manager = None

# Active chatbot instances: session_id -> PersonaChatbot
chatbots = {} 
# Pending ZIP operations: zip_id -> extraction info (global is fine for temp ops)
pending_zips = {} 

# --- Helper Functions ---

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Defaults
    return {
        "chatbot_model": "gemini-2.0-flash",
        "training_model": "gemini-2.0-flash",
        "embedding_model": "text-embedding-004",
        "image_model": "gemini-2.0-flash" # Default image model
    }

def save_settings(new_settings):
    # Merge with existing
    current = load_settings()
    current.update(new_settings)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(current, f, indent=2)

def get_gemini_client():
    global _gemini_model
    # Always check for fresh key
    api_key = get_gemini_key() or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
        
    return genai.Client(api_key=api_key)

def get_gemini_model_name():
    settings = load_settings()
    return settings.get("chatbot_model", "gemini-2.0-flash")

def get_wavespeed_manager(force_reload: bool = False):
    global _wavespeed_manager
    if _wavespeed_manager is None or force_reload:
        api_key = get_wavespeed_key()
        if not api_key:
            return None
        _wavespeed_manager = WaveSpeedManager(api_key=api_key)
    return _wavespeed_manager

def get_session_dir(session_id: str) -> Path:
    return CHATS_DIR / session_id

def get_session_uploads_dir(session_id: str, file_type: str = None) -> Path:
    base = get_session_dir(session_id) / "uploads"
    if file_type:
        return base / file_type
    return base

def get_session_preprocessed_dir(session_id: str) -> Path:
    return get_session_dir(session_id) / "preprocessed"

def load_session_metadata(session_id: str):
    session_file = get_session_dir(session_id) / "session.json"
    if session_file.exists():
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
    return None

def save_session_metadata(session_id: str, data: dict):
    session_dir = get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    with open(session_dir / "session.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_message_history(session_id: str):
    history_file = get_session_dir(session_id) / "history.json"
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_message_history(session_id: str, messages: list):
    history_file = get_session_dir(session_id) / "history.json"
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2)

# Update get_or_create_chatbot to set image model
def get_or_create_chatbot(session_id: str):
    """Get existing chatbot or create new one for session."""
    if session_id in chatbots:
        # Update settings just in case they changed
        settings = load_settings()
        chatbots[session_id].set_image_model(settings.get("image_model", "gemini-2.0-flash"))
        return chatbots[session_id]
        
    session_data = load_session_metadata(session_id)
    if not session_data:
        return None
        
    # Determine subject from session data or preprocessed files
    subject = session_data.get("subject")
    
    preprocessed_dir = get_session_preprocessed_dir(session_id)
    if not preprocessed_dir.exists():
        return None

    # Find definition files if subject not explicitly set (legacy compat) or just check existence
    # We look for ANY *_style_summary.txt to identify the subject name used during generation
    summary_files = list(preprocessed_dir.glob("*_style_summary.txt"))
    if not summary_files:
        return None
        
    # Use the first found summary file to determine subject if needed
    summary_path = summary_files[0]
    subject_name = summary_path.name.replace("_style_summary.txt", "")
    
    embeddings_path = preprocessed_dir / f"{subject_name}_embeddings.json"
    
    if not embeddings_path.exists():
        return None
        
    try:
        client = get_gemini_client()
        model_name = get_gemini_model_name()
        settings = load_settings()
        
        chatbot = PersonaChatbot(
            str(summary_path),
            str(embeddings_path),
            client=client,
            model_name=model_name
        )
        chatbot.set_image_model(settings.get("image_model", "gemini-2.0-flash"))
        chatbots[session_id] = chatbot
        return chatbot
    except Exception as e:
        print(f"Failed to create chatbot for {session_id}: {e}")
        return None

# --- File Processing Helpers ---

def compute_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def extract_message_fingerprints(file_path, n=20):
    """Reuse existing logic but robust to path."""
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

def scan_session_uploads(session_id, file_type):
    folder = get_session_uploads_dir(session_id, file_type)
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
                    if 'original_name' in meta_data:
                        metadata['original_name'] = meta_data['original_name']
            files.append(metadata)
        except Exception as e:
            print(f"Error scanning file {file_path}: {e}")
    return files

def get_session_images_dir(session_id: str) -> Path:
    d = get_session_dir(session_id) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d

# --- API Endpoints: Sessions (CRUD) ---

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions = []
    if CHATS_DIR.exists():
        for session_dir in CHATS_DIR.iterdir():
            if session_dir.is_dir():
                s = load_session_metadata(session_dir.name)
                if s: sessions.append(s)
    # Sort by created_at desc
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"sessions": sessions})

@app.route("/api/sessions", methods=["POST"])
def create_session():
    # Initialize a new session
    session_id = uuid.uuid4().hex[:8]
    data = request.json or {}
    name = data.get("name", "New Chat")
    
    session_data = {
        "id": session_id,
        "name": name,
        "created_at": datetime.now().isoformat(),
        "preview": "No messages yet.",
        "subject": None, # Will be set during refresh/processing
        "wavespeed_voice_id": None
    }
    
    save_session_metadata(session_id, session_data)
    save_message_history(session_id, [])
    
    # Create directory structure
    get_session_uploads_dir(session_id, "text").mkdir(parents=True, exist_ok=True)
    get_session_uploads_dir(session_id, "voice").mkdir(parents=True, exist_ok=True)
    get_session_preprocessed_dir(session_id).mkdir(parents=True, exist_ok=True)
    get_session_images_dir(session_id).mkdir(parents=True, exist_ok=True)
    
    return jsonify(session_data)

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    session_dir = get_session_dir(session_id)
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
            if session_id in chatbots:
                del chatbots[session_id]
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Session not found"}), 404

# --- API Endpoints: Per-Chat Files ---

@app.route("/api/chats/<session_id>/files/<file_type>", methods=["GET"])
def list_chat_files(session_id, file_type):
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid type"}), 400
    files = scan_session_uploads(session_id, file_type)
    return jsonify({"files": files, "count": len(files)})

@app.route("/api/chats/<session_id>/files/<file_type>", methods=["POST"])
def upload_chat_files(session_id, file_type):
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid file type"}), 400
    
    folder = get_session_uploads_dir(session_id, file_type)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400
        
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
                
            if new_fingerprints:
                batch_fingerprints[file.filename] = new_fingerprints
        
        # ZIP handling (Deferred interaction via return)
        if file_type == "text" and file_ext == '.zip':
             # Simplified for brevity - reuse logic
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
                        "session_id": session_id,
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
                        "session_id": session_id,
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

        # Standard processing
        try:
            detected_type = classify_file(str(file_path)) if file_type == "text" else "voice"
            participants = extract_participants(str(file_path), detected_type) if file_type == "text" else []
            
            uploaded.append({
                "id": file_id, "original_name": file.filename, "saved_as": unique_name,
                "file_type": file_type, "detected_type": detected_type, "participants": participants
            })
        except Exception:
            uploaded.append({"id": file_id, "file_type": file_type, "saved_as": unique_name})

    return jsonify({
        "success": True, "uploaded": uploaded, "rejected": rejected,
        "uploaded_count": len(uploaded)
    })

@app.route("/api/chats/zip/select", methods=["POST"])
def select_zip_conversations():
    data = request.get_json()
    zip_id = data.get("zip_id")
    selected_folders = data.get("conversations", [])
    
    if not zip_id or zip_id not in pending_zips:
        return jsonify({"error": "ZIP not found"}), 404
        
    zip_info = pending_zips[zip_id]
    session_id = zip_info.get("session_id")
    if not session_id:
        return jsonify({"error": "Session context lost"}), 400

    conversations = zip_info["conversations"]
    zip_type = zip_info.get("zip_type", "instagram")
    
    selected_convs = [c for c in conversations if c["folder_name"] in selected_folders]
    uploaded = []
    rejected = []
    
    folder = get_session_uploads_dir(session_id, "text")
    folder.mkdir(parents=True, exist_ok=True)
    
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

@app.route("/api/chats/<session_id>/files/<file_type>/<file_id>", methods=["DELETE"])
def delete_chat_file(session_id, file_type, file_id):
    folder = get_session_uploads_dir(session_id, file_type)
    matches = list(folder.glob(f"{file_id}.*"))
    deleted = False
    for p in matches:
        p.unlink()
        deleted = True
    (folder / f"{file_id}.meta.json").unlink(missing_ok=True)
    
    if not deleted: return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})

@app.route("/api/chats/<session_id>/files/text/<file_id>/subject", methods=["POST"])
def set_chat_file_subject(session_id, file_id):
    folder = get_session_uploads_dir(session_id, "text")
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

@app.route("/api/chats/<session_id>/files/voice/<file_id>/preview", methods=["GET"])
def preview_voice_file(session_id, file_id):
    """Serve a voice file for audio preview."""
    folder = get_session_uploads_dir(session_id, "voice")
    matches = list(folder.glob(f"{file_id}.*"))
    # Filter out .meta.json files
    audio_files = [p for p in matches if not p.name.endswith('.meta.json')]
    
    if not audio_files:
        return jsonify({"error": "Not found"}), 404
    
    file_path = audio_files[0]
    return send_from_directory(file_path.parent, file_path.name)

# --- API Endpoints: Processing & Refresh ---

@app.route("/api/chats/<session_id>/refresh/ready", methods=["GET"])
def check_chat_refresh_ready(session_id):
    files = scan_session_uploads(session_id, "text")
    if not files:
        return jsonify({"ready": False, "reason": "No files uploaded"})
    files_with_subject = [f for f in files if f.get("subject")]
    if len(files_with_subject) < len(files):
        return jsonify({"ready": False, "reason": "Missing subjects"})
    return jsonify({"ready": True})

@app.route("/api/chats/<session_id>/refresh", methods=["POST"])
def refresh_chat_memory(session_id):
    # This logic runs the processing PIPELINE for the specific session
    session_data = load_session_metadata(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    
    # Get additional context from request body
    request_data = request.get_json() or {}
    additional_context = request_data.get("additional_context", "")

    def generate():
        try:
            yield f"data: {json.dumps({'step': 'starting', 'progress': 0, 'message': 'Starting refresh...'})}\n\n"
            
            # 1. Text Processing
            processed_dir = get_session_preprocessed_dir(session_id)
            files = scan_session_uploads(session_id, "text")
            
            # Group by subject
            subject_files = {}
            for f in files:
                sub = f.get("subject", "Unknown")
                if sub not in subject_files: subject_files[sub] = []
                subject_files[sub].append(f)
            
            # For this version, we completely wipe and re-process. 
            # Smart hashing could be added, but per-chat is small enough to be fast usually.
            yield f"data: {json.dumps({'step': 'cleaning', 'progress': 10, 'message': 'Cleaning old data...'})}\n\n"
            for p in processed_dir.glob("*"): p.unlink()
            
            total = len(subject_files)
            main_subject = None
            
            for idx, (subject, s_files) in enumerate(subject_files.items()):
                if not main_subject: main_subject = subject # Pick first as primary? or logic needed
                
                yield f"data: {json.dumps({'step': 'processing', 'progress': 20, 'message': f'Processing {subject}...'})}\n\n"
                
                results = [(f["original_name"], f["path"], f["detected_type"], subject) for f in s_files]
                
                # Style Generation
                temp_style = processed_dir / f"{subject}_style_temp.txt"
                generate_style_file(results, str(temp_style))
                
                # Context Chunks
                chunks_path = processed_dir / f"{subject}_context_chunks.json"
                generate_context_chunks(results, str(chunks_path))
                
                # Style Summary
                yield f"data: {json.dumps({'step': 'summary', 'progress': 50, 'message': f'Analyzing style for {subject}...'})}\n\n"
                summary_path = processed_dir / f"{subject}_style_summary.txt"
                
                settings = load_settings()
                train_model = settings.get("training_model", "gemini-3-flash-preview")
                
                client = get_gemini_client()
                
                generate_style_summary(str(temp_style), str(summary_path), subject, client=client, model_name=train_model, additional_context=additional_context)
                
                # Embeddings
                yield f"data: {json.dumps({'step': 'embeddings', 'progress': 70, 'message': f'Generating embeddings for {subject}...'})}\n\n"
                embeddings_path = processed_dir / f"{subject}_embeddings.json"
                
                settings = load_settings()
                embed_model = settings.get("embedding_model", "text-embedding-004")
                
                generate_embeddings(str(chunks_path), str(embeddings_path), client=client, model_name=embed_model)
                
                if temp_style.exists(): temp_style.unlink()
            
            # Update session subject if needed
            if main_subject:
                session_data["subject"] = main_subject
                save_session_metadata(session_id, session_data)
                
                # Invalidate existing chatbot
                if session_id in chatbots:
                    del chatbots[session_id]
            
            # 2. Voice Cloning
            voice_result = None
            voice_files = scan_session_uploads(session_id, "voice")
            voice_files.sort(key=lambda x: os.path.getmtime(x["path"]), reverse=True)
            
            if voice_files:
                api_key = get_wavespeed_key()
                manager = get_wavespeed_manager()
                
                if api_key and manager:
                    yield f"data: {json.dumps({'step': 'voice', 'progress': 80, 'message': 'Cloning voice...'})}\n\n"
                    target_file = voice_files[0]
                    
                    try:
                        clean_name = "".join(c for c in session_data["name"] if c.isalnum())
                        voice_name_id = f"NullTale{session_id[-6:]}{clean_name}"
                        
                        voice_id = manager.clone_voice(voice_name_id, target_file["path"])
                        
                        now = datetime.now().isoformat()
                        session_data["wavespeed_voice_id"] = voice_id
                        session_data["voice_created_at"] = now
                        session_data["voice_last_used_at"] = now
                        save_session_metadata(session_id, session_data)
                        
                        # Cleanup used voice file
                        Path(target_file["path"]).unlink()
                        
                        voice_result = {"success": True, "message": "Voice cloned successfully"}
                    except Exception as e:
                        voice_result = {"error": str(e)}
            
            yield f"data: {json.dumps({'step': 'complete', 'progress': 100, 'message': 'Refresh complete!', 'voice_cloning': voice_result})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# --- API Endpoints: Chat & Voice Status ---

@app.route("/api/messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    messages = load_message_history(session_id)
    return jsonify({"messages": messages})

@app.route("/api/chat/<session_id>/images/<filename>", methods=["GET"])
def get_chat_image(session_id, filename):
    folder = get_session_images_dir(session_id)
    return send_file(folder / filename)

@app.route("/api/chat", methods=["POST"])
def send_message():
    # Handle multipart/form-data for images
    content = ""
    session_id = ""
    image_file = None
    
    if request.content_type and "multipart/form-data" in request.content_type:
        content = request.form.get("content", "").strip()
        session_id = request.form.get("session_id")
        if "image" in request.files:
            image_file = request.files["image"]
    else:
        # JSON fallback
        data = request.json
        content = data.get("content", "").strip()
        session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
        
    messages = load_message_history(session_id)
    images_dir = get_session_images_dir(session_id)
    
    # Process User Image
    user_image_path = None
    user_image_filename = None
    from PIL import Image # Lazy import
    import io
    pil_image = None

    if image_file:
        file_ext = Path(image_file.filename).suffix
        if not file_ext: file_ext = ".jpg"
        user_image_filename = f"user_{uuid.uuid4().hex[:8]}{file_ext}"
        user_image_path = images_dir / user_image_filename
        image_file.save(str(user_image_path))
        
        # Open for Gemini
        try:
            pil_image = Image.open(str(user_image_path))
        except Exception as e:
            print(f"Error opening user image: {e}")

    # User message object
    user_msg_obj = {
        "id": uuid.uuid4().hex[:8],
        "role": "user",
        "content": content,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "images": [f"/api/chat/{session_id}/images/{user_image_filename}"] if user_image_filename else []
    }
    messages.append(user_msg_obj)
    
    # Get AI response
    chatbot = get_or_create_chatbot(session_id)
    
    if not chatbot:
        return jsonify({
            "user_message": user_msg_obj,
            "ai_message": {
               "id": uuid.uuid4().hex[:8], "role": "assistant", "content": "I'm not ready yet.", "timestamp": ""
            }
        })

    # Track user image in chatbot's image history for context
    if pil_image and user_image_filename:
        user_img_id = user_image_filename.replace("user_", "").split(".")[0]
        chatbot.image_history.append({
            "id": user_img_id,
            "description": f"Image sent by user with message: {content[:50]}",
            "source": "user",
            "pil_image": pil_image  # Keep reference for editing
        })

    # Call Chatbot with optional image
    # Note: chatbot.chat() is now synchronous and returns a dict with 'text' and 'images' list
    response_data = chatbot.chat(content, user_image=pil_image)
    
    ai_text = response_data.get("text", "")
    ai_generated_images = response_data.get("images", []) # list of {id, bytes, prompt}
    
    saved_ai_images = []
    
    # Save generated images and store PIL data for future editing
    for img_data in ai_generated_images:
        img_filename = f"ai_{img_data['id']}.png" # Default to png
        save_path = images_dir / img_filename
        
        with open(save_path, "wb") as f:
            f.write(img_data["bytes"])
            
        saved_ai_images.append(f"/api/chat/{session_id}/images/{img_filename}")
        
        # Store PIL image reference for future editing
        try:
            pil_ai_image = Image.open(io.BytesIO(img_data["bytes"]))
            # Find this image in chatbot's history and add PIL reference
            for img_hist in chatbot.image_history:
                if img_hist['id'] == img_data['id']:
                    img_hist['pil_image'] = pil_ai_image
                    break
        except Exception as e:
            print(f"[DEBUG] Could not create PIL image for editing: {e}")
    
    # Split AI text into multiple messages by line breaks
    # This creates the "chat bubble per line" effect
    # Filter out IMG file attachment lines
    ai_lines = []
    for line in ai_text.split('\n'):
        line = line.strip()
        if line:
            # Filter out "IMG-xxx.png (file attached)" type messages
            if 'IMG-' in line and '(file attached)' in line:
                continue
            if line.startswith('IMG-') and '.png' in line:
                continue
            ai_lines.append(line)
    
    ai_messages = []
    timestamp = datetime.now().strftime("%I:%M %p")
    
    if ai_lines:
        # First message gets any images
        for i, line in enumerate(ai_lines):
            msg = {
                "id": uuid.uuid4().hex[:8],
                "role": "assistant",
                "content": line,
                "timestamp": timestamp,
                "images": saved_ai_images if i == 0 else []  # Images only on first message
            }
            ai_messages.append(msg)
            messages.append(msg)
    else:
        # If no text but have images, create one message for images
        if saved_ai_images:
            msg = {
                "id": uuid.uuid4().hex[:8],
                "role": "assistant",
                "content": "",
                "timestamp": timestamp,
                "images": saved_ai_images
            }
            ai_messages.append(msg)
            messages.append(msg)
    
    save_message_history(session_id, messages)
    
    # Update preview text
    session_data = load_session_metadata(session_id)
    if session_data:
        preview_text = ai_lines[0] if ai_lines else "[Sent an image]"
        session_data["preview"] = preview_text[:50] + "..." if len(preview_text) > 50 else preview_text
        save_session_metadata(session_id, session_data)
        
    return jsonify({
        "user_message": user_msg_obj,
        "ai_message": ai_messages[0] if ai_messages else {"id": "", "role": "assistant", "content": "", "timestamp": "", "images": []},
        "ai_messages": ai_messages  # Array of all split messages
    })

@app.route("/api/messages/<session_id>", methods=["DELETE"])
def delete_messages(session_id):
    """Clear chat history for a session."""
    messages = []
    save_message_history(session_id, messages)
    
    # Also clear chatbot history if active
    if session_id in chatbots:
        chatbots[session_id].reset_history()
        
    return jsonify({"status": "ok", "message": "History cleared"})

@app.route("/api/voice/clone/<session_id>", methods=["POST"])
def get_voice_status(session_id):
    session_data = load_session_metadata(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
        
    voice_id = session_data.get("wavespeed_voice_id")
    
    if not voice_id:
        return jsonify({"has_voice": False, "voice_status": "none", "message": "No voice configured"})
        
    last_used = session_data.get("voice_last_used_at") or session_data.get("voice_created_at")
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

@app.route("/api/settings", methods=["GET"])
def get_user_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["PUT"])
def update_user_settings():
    new_settings = request.json
    save_settings(new_settings)
    return jsonify(load_settings())

@app.route("/api/settings/wavespeed-key", methods=["GET"])
def check_wavespeed_key():
    return jsonify({"configured": has_wavespeed_key()})

@app.route("/api/settings/wavespeed-key", methods=["POST"])
def set_wavespeed_key():
    key = request.json.get("api_key")
    if not key: return jsonify({"error": "No key provided"}), 400
    if save_wavespeed_key(key):
        return jsonify({"success": True})
    return jsonify({"error": "Failed to save"}), 500

@app.route("/api/settings/wavespeed-key", methods=["DELETE"])
def remove_wavespeed_key():
    delete_secret("wavespeed_api_key")
    return jsonify({"success": True})

@app.route("/api/settings/gemini-key", methods=["GET"])
def check_gemini_key():
    return jsonify({"configured": has_gemini_key()})

@app.route("/api/settings/gemini-key", methods=["POST"])
def set_gemini_key():
    key = request.json.get("api_key")
    if not key: return jsonify({"error": "No key provided"}), 400
    if save_gemini_key(key):
        return jsonify({"success": True})
    return jsonify({"error": "Failed to save"}), 500

@app.route("/api/settings/gemini-key", methods=["DELETE"])
def remove_gemini_key():
    delete_secret("gemini_api_key")
    return jsonify({"success": True})

@app.route("/api/warmup", methods=["GET", "POST"])
def warmup():
    return jsonify({"status": "ok", "message": "Backend online"})

@app.route("/api/call/stream", methods=["POST"])
def stream_voice_call():
    print("\n" + "="*60)
    print("[VOICE DEBUG] Voice call request received")
    
    data = request.json
    content = data.get("content", "").strip()
    session_id = data.get("session_id")
    
    print(f"[VOICE DEBUG] Session ID: {session_id}")
    print(f"[VOICE DEBUG] Content: '{content[:50]}...' (len={len(content)})")
    
    if not content or not session_id:
        print("[VOICE DEBUG] ERROR: Missing content or session_id")
        return jsonify({"error": "Missing content or session_id"}), 400
        
    chatbot = get_or_create_chatbot(session_id)
    if not chatbot:
        print("[VOICE DEBUG] ERROR: Chatbot not ready")
        return jsonify({"error": "Chatbot not ready. Please refresh memory."}), 400
    print(f"[VOICE DEBUG] Chatbot ready: {chatbot.subject}")
        
    ws_manager = get_wavespeed_manager()
    if not ws_manager:
        print("[VOICE DEBUG] ERROR: Voice service (WaveSpeed) not configured")
        return jsonify({"error": "Voice service not configured"}), 400
    print("[VOICE DEBUG] WaveSpeed manager initialized")
    
    # Get voice ID
    session_data = load_session_metadata(session_id) or {}
    voice_id = session_data.get("wavespeed_voice_id", "Deep_Voice_Man")
    print(f"[VOICE DEBUG] Voice ID: {voice_id}")
    
    # Check voice status
    voice_created_at = session_data.get("voice_created_at")
    print(f"[VOICE DEBUG] Voice created at: {voice_created_at}")
    if voice_created_at:
        try:
            from datetime import datetime, timedelta
            created_dt = datetime.fromisoformat(voice_created_at)
            days_old = (datetime.now() - created_dt).days
            print(f"[VOICE DEBUG] Voice age: {days_old} days (expires after 7 days)")
            if days_old >= 7:
                print("[VOICE DEBUG] WARNING: Voice may be expired!")
        except Exception as e:
            print(f"[VOICE DEBUG] Could not parse voice date: {e}")
    
    def generate():
        import re
        import json
        
        def clean_for_tts(text):
            """Clean text for TTS - remove ellipsis, repeated chars, etc."""
            # Remove ellipsis (... or more dots)
            text = re.sub(r'\.{2,}', '.', text)
            # Remove multiple exclamation/question marks
            text = re.sub(r'!{2,}', '!', text)
            text = re.sub(r'\?{2,}', '?', text)
            # Remove asterisk actions like *laughs*
            text = re.sub(r'\*[^*]+\*', '', text)
            # Clean up repeated letters (hiiiii -> hii)
            text = re.sub(r'(.)\1{2,}', r'\1\1', text)
            # Clean up double spaces
            text = re.sub(r' {2,}', ' ', text)
            return text.strip()
        
        full_response_text = ""
        
        yield f"data: {json.dumps({'type': 'status', 'content': 'processing'})}\n\n"
        
        try:
            print("[VOICE DEBUG] Starting stream_chat_voice...")
            
            # Collect full response from Gemini (voice call = single complete response)
            chunk_count = 0
            for chunk in chatbot.stream_chat_voice(content):
                chunk_count += 1
                if chunk_count == 1:
                    print(f"[VOICE DEBUG] First text chunk received: '{chunk[:50]}...'")
                # Send text event for UI display
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                full_response_text += chunk
            
            print(f"[VOICE DEBUG] Total text chunks received: {chunk_count}")
            print(f"[VOICE DEBUG] Full response length: {len(full_response_text)}")
            
            if chunk_count == 0:
                print("[VOICE DEBUG] WARNING: No text chunks from stream_chat_voice!")
            
            # Clean and send full response to TTS (no sentence splitting)
            if full_response_text.strip():
                clean_text = clean_for_tts(full_response_text)
                if clean_text:
                    try:
                        print(f"[VOICE DEBUG] Sending to TTS (full): '{clean_text[:50]}...'")
                        for audio_chunk in ws_manager.speak_stream(clean_text, voice_id):
                            b64_audio = base64.b64encode(audio_chunk).decode('utf-8')
                            yield f"data: {json.dumps({'type': 'audio', 'content': b64_audio, 'index': 0})}\n\n"
                    except Exception as e:
                        print(f"[VOICE DEBUG] TTS Error: {type(e).__name__}: {e}")
                        yield f"data: {json.dumps({'type': 'error', 'content': f'TTS Error: {e}'})}\n\n"

            print(f"[VOICE DEBUG] Stream complete.")
            yield f"data: {json.dumps({'type': 'done', 'full_text': full_response_text})}\n\n"

        except Exception as e:
            print(f"[VOICE DEBUG] Stream Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == "__main__":
    app.run(debug=True, port=5000)
