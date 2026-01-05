"""
NullTale Backend API - Flask Server
Provides API endpoints for file upload, classification, and participant extraction.
"""

import os
import sys
import uuid
import hashlib
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load .env from root Nulltale folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Import processing modules
from processor import classify_file, extract_participants
from instagram_zip_processor import (
    extract_zip, find_conversations, merge_conversation_messages, cleanup_zip
)

app = Flask(__name__)

# CORS for Vite dev server
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

# Configure upload directory
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "text").mkdir(exist_ok=True)
(UPLOAD_DIR / "voice").mkdir(exist_ok=True)

# Allowed extensions for text files
ALLOWED_TEXT_EXTENSIONS = {'.txt', '.json', '.zip'}

# Storage for pending ZIP uploads (zip_id -> extraction info)
pending_zips = {}


def compute_file_hash(file_path):
    """Compute SHA256 hash of a file's content."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def get_existing_hashes(folder):
    """Get hashes of all existing files in a folder."""
    hashes = {}
    if not folder.exists():
        return hashes
    
    for file_path in folder.iterdir():
        if file_path.is_file() and not file_path.name.endswith('.meta.json'):
            try:
                file_hash = compute_file_hash(file_path)
                hashes[file_hash] = file_path.name
            except Exception:
                pass
    return hashes


def get_file_metadata(file_path):
    """Get metadata for a file including type detection and participants."""
    path = Path(file_path)
    file_id = path.stem  # Use filename without extension as ID
    
    detected_type = classify_file(str(path))
    participants = []
    if detected_type in ["WhatsApp", "Instagram"]:
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
    """Scan uploads folder and return all files with metadata."""
    folder = UPLOAD_DIR / file_type
    if not folder.exists():
        return []
    
    files = []
    for file_path in folder.iterdir():
        # Skip meta files and non-files
        if not file_path.is_file():
            continue
        if file_path.name.endswith('.meta.json'):
            continue
        
        try:
            metadata = get_file_metadata(file_path)
            
            # Load subject from meta file if exists
            meta_file = folder / f"{metadata['id']}.meta.json"
            if meta_file.exists():
                import json
                with open(meta_file, 'r') as f:
                    meta_data = json.load(f)
                    metadata['subject'] = meta_data.get('subject')
            
            files.append(metadata)
        except Exception as e:
            print(f"Error scanning file {file_path}: {e}")
    
    return files


# --- File Upload Endpoints ---

@app.route("/api/files/<file_type>", methods=["POST"])
def upload_files(file_type):
    """
    Upload one or more files. For text files, validates that they are 
    WhatsApp or Instagram exports before saving. Also checks for duplicates.
    Returns list of uploaded files with their metadata.
    """
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid file type"}), 400
    
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    # Get all files (supports multiple)
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400
    
    # Get hashes of existing files to detect duplicates
    folder = UPLOAD_DIR / file_type
    existing_hashes = get_existing_hashes(folder)
    # Track hashes of newly uploaded files in this batch
    batch_hashes = {}
    
    uploaded = []
    rejected = []
    
    for file in files:
        if file.filename == "":
            continue
        
        original_name = secure_filename(file.filename)
        file_ext = Path(original_name).suffix.lower()
        
        # Validate extension for text files
        if file_type == "text" and file_ext not in ALLOWED_TEXT_EXTENSIONS:
            rejected.append({
                "name": file.filename,
                "reason": f"Only .txt and .json files are accepted"
            })
            continue
        
        # Generate unique filename
        file_id = uuid.uuid4().hex[:12]
        unique_name = f"{file_id}{file_ext}"
        file_path = UPLOAD_DIR / file_type / unique_name
        
        # Save file temporarily to check type and hash
        file.save(str(file_path))
        
        # Check for duplicate content
        file_hash = compute_file_hash(file_path)
        
        if file_hash in existing_hashes:
            # Duplicate of existing file
            file_path.unlink()
            rejected.append({
                "name": file.filename,
                "reason": "Duplicate file. This content has already been uploaded."
            })
            continue
        
        if file_hash in batch_hashes:
            # Duplicate within this upload batch
            file_path.unlink()
            rejected.append({
                "name": file.filename,
                "reason": f"Duplicate of {batch_hashes[file_hash]} in this upload."
            })
            continue
        
        # For text files, validate it's WhatsApp or Instagram (or ZIP)
        if file_type == "text":
            # Handle ZIP files specially
            if file_ext == '.zip':
                try:
                    # Extract and find conversations
                    zip_id = file_id
                    extracted_path = extract_zip(str(file_path), zip_id)
                    conversations = find_conversations(extracted_path)
                    
                    if not conversations:
                        # No valid Instagram conversations found
                        file_path.unlink()
                        cleanup_zip(zip_id)
                        rejected.append({
                            "name": file.filename,
                            "reason": "No Instagram conversations found in ZIP. Make sure this is an Instagram data export."
                        })
                        continue
                    
                    # Store the ZIP info for later selection
                    pending_zips[zip_id] = {
                        "zip_path": str(file_path),
                        "extracted_path": str(extracted_path),
                        "original_name": file.filename,
                        "conversations": conversations
                    }
                    
                    # Return special response for ZIP
                    return jsonify({
                        "success": True,
                        "type": "zip_upload",
                        "zip_id": zip_id,
                        "original_name": file.filename,
                        "conversations": conversations,
                        "uploaded": [],
                        "rejected": rejected
                    })
                    
                except Exception as e:
                    file_path.unlink()
                    rejected.append({
                        "name": file.filename,
                        "reason": f"Failed to process ZIP file: {str(e)}"
                    })
                    continue
            
            detected_type = classify_file(str(file_path))
            
            if detected_type not in ["WhatsApp", "Instagram"]:
                # Delete the file and reject
                file_path.unlink()
                rejected.append({
                    "name": file.filename,
                    "reason": "Not a supported chat file. Please upload WhatsApp exports (.txt), Instagram exports (.json), or Instagram ZIP exports."
                })
                continue
            
            # Get participants
            participants = extract_participants(str(file_path), detected_type)
            
            uploaded.append({
                "id": file_id,
                "original_name": file.filename,
                "saved_as": unique_name,
                "file_type": file_type,
                "detected_type": detected_type,
                "participants": participants,
                "subject": None,
                "path": str(file_path),
                "size": file_path.stat().st_size
            })
            # Track this file's hash for batch duplicate detection
            batch_hashes[file_hash] = file.filename
        else:
            # Voice files - just save
            uploaded.append({
                "id": file_id,
                "original_name": file.filename,
                "saved_as": unique_name,
                "file_type": file_type,
                "detected_type": "voice",
                "participants": [],
                "subject": None,
                "path": str(file_path),
                "size": file_path.stat().st_size
            })
            # Track this file's hash for batch duplicate detection
            batch_hashes[file_hash] = file.filename
    
    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "rejected": rejected,
        "uploaded_count": len(uploaded),
        "rejected_count": len(rejected)
    })


@app.route("/api/files/text/zip/select", methods=["POST"])
def select_zip_conversations():
    """
    Select conversations from a previously uploaded ZIP file.
    Request body: { "zip_id": "...", "conversations": ["folder_name1", "folder_name2"] }
    """
    import json as json_module
    
    data = request.get_json()
    zip_id = data.get("zip_id")
    selected_folders = data.get("conversations", [])
    
    if not zip_id or zip_id not in pending_zips:
        return jsonify({"error": "ZIP not found or expired"}), 404
    
    if not selected_folders:
        return jsonify({"error": "No conversations selected"}), 400
    
    zip_info = pending_zips[zip_id]
    conversations = zip_info["conversations"]
    
    # Find selected conversations by folder name
    selected_convs = [c for c in conversations if c["folder_name"] in selected_folders]
    
    if not selected_convs:
        return jsonify({"error": "Selected conversations not found"}), 400
    
    uploaded = []
    rejected = []
    folder = UPLOAD_DIR / "text"
    existing_hashes = get_existing_hashes(folder)
    
    for conv in selected_convs:
        try:
            # Merge all message files into one JSON
            merged_data = merge_conversation_messages(conv["path"])
            
            if not merged_data:
                rejected.append({
                    "name": conv["display_name"],
                    "reason": "Failed to merge conversation messages"
                })
                continue
            
            # Generate unique filename
            file_id = uuid.uuid4().hex[:12]
            file_name = f"{file_id}.json"
            file_path = folder / file_name
            
            # Save merged JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json_module.dump(merged_data, f, ensure_ascii=False)
            
            # Check for duplicates
            file_hash = compute_file_hash(file_path)
            if file_hash in existing_hashes:
                file_path.unlink()
                rejected.append({
                    "name": conv["display_name"],
                    "reason": "Duplicate conversation already uploaded"
                })
                continue
            
            # Get participants from merged data
            participants = []
            if 'participants' in merged_data:
                for p in merged_data['participants']:
                    name = p.get('name', 'Unknown')
                    try:
                        name = name.encode('latin-1').decode('utf-8')
                    except:
                        pass
                    participants.append(name)
            
            uploaded.append({
                "id": file_id,
                "original_name": f"{conv['display_name']} (from ZIP)",
                "saved_as": file_name,
                "file_type": "text",
                "detected_type": "Instagram",
                "participants": participants,
                "subject": None,
                "path": str(file_path),
                "size": file_path.stat().st_size
            })
            
        except Exception as e:
            rejected.append({
                "name": conv["display_name"],
                "reason": f"Error processing: {str(e)}"
            })
    
    # Cleanup: delete ZIP file and temp extraction
    try:
        zip_path = Path(zip_info["zip_path"])
        if zip_path.exists():
            zip_path.unlink()
        cleanup_zip(zip_id)
    except Exception as e:
        print(f"Cleanup error: {e}")
    
    # Remove from pending
    del pending_zips[zip_id]
    
    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "rejected": rejected,
        "uploaded_count": len(uploaded),
        "rejected_count": len(rejected)
    })

@app.route("/api/files/<file_type>", methods=["GET"])
def list_files(file_type):
    """List all files in uploads folder by type - direct folder scan."""
    if file_type not in ["text", "voice"]:
        return jsonify({"error": "Invalid file type"}), 400
    
    # Scan folder directly for real-time sync
    files = scan_uploads_folder(file_type)
    
    return jsonify({
        "files": files,
        "count": len(files)
    })


@app.route("/api/files/<file_type>/<file_id>/participants", methods=["GET"])
def get_participants(file_type, file_id):
    """Get participants for an uploaded file."""
    folder = UPLOAD_DIR / file_type
    
    # Find file by ID prefix
    matching_files = list(folder.glob(f"{file_id}.*"))
    if not matching_files:
        return jsonify({"error": "File not found"}), 404
    
    file_path = matching_files[0]
    detected_type = classify_file(str(file_path))
    participants = []
    if detected_type in ["WhatsApp", "Instagram"]:
        participants = extract_participants(str(file_path), detected_type)
    
    return jsonify({
        "file_id": file_id,
        "participants": participants,
        "detected_type": detected_type
    })


@app.route("/api/files/<file_type>/<file_id>/subject", methods=["POST"])
def set_subject(file_type, file_id):
    """Set the subject for an uploaded file (stored in a metadata file)."""
    folder = UPLOAD_DIR / file_type
    
    # Find file by ID prefix
    matching_files = list(folder.glob(f"{file_id}.*"))
    if not matching_files:
        return jsonify({"error": "File not found"}), 404
    
    data = request.get_json()
    subject = data.get("subject")
    
    if not subject:
        return jsonify({"error": "Subject is required"}), 400
    
    # Store subject in a metadata JSON file
    meta_file = folder / f"{file_id}.meta.json"
    import json
    meta_data = {"subject": subject}
    with open(meta_file, 'w') as f:
        json.dump(meta_data, f)
    
    return jsonify({
        "success": True,
        "file_id": file_id,
        "subject": subject
    })


@app.route("/api/files/<file_type>/<file_id>", methods=["DELETE"])
def delete_file(file_type, file_id):
    """Delete an uploaded file."""
    folder = UPLOAD_DIR / file_type
    
    # Find and delete file by ID prefix
    matching_files = list(folder.glob(f"{file_id}.*"))
    if not matching_files:
        return jsonify({"error": "File not found"}), 404
    
    for file_path in matching_files:
        file_path.unlink()
    
    # Also delete metadata file if exists
    meta_file = folder / f"{file_id}.meta.json"
    if meta_file.exists():
        meta_file.unlink()
    
    return jsonify({
        "success": True,
        "deleted_id": file_id
    })


# --- Health Check ---

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "nulltale-api"
    })


# --- Processing Endpoints ---

PREPROCESSED_DIR = Path(__file__).parent / "preprocessed"
PREPROCESSED_DIR.mkdir(exist_ok=True)


@app.route("/api/refresh/ready", methods=["GET"])
def check_refresh_ready():
    """Check if we're ready to process (all files have subjects selected)."""
    files = scan_uploads_folder("text")
    
    if not files:
        return jsonify({
            "ready": False,
            "reason": "No files uploaded",
            "files_count": 0,
            "files_with_subject": 0
        })
    
    files_with_subject = [f for f in files if f.get("subject")]
    
    if len(files_with_subject) < len(files):
        return jsonify({
            "ready": False,
            "reason": "Some files don't have a subject selected",
            "files_count": len(files),
            "files_with_subject": len(files_with_subject)
        })
    
    return jsonify({
        "ready": True,
        "files_count": len(files),
        "files_with_subject": len(files_with_subject)
    })


@app.route("/api/refresh", methods=["POST"])
def process_files():
    """
    Process all uploaded files through the preprocessing pipeline.
    Returns SSE stream with progress updates.
    """
    from flask import Response, stream_with_context
    import json as json_module
    import shutil
    
    # Import processing modules
    from processor import generate_style_file, generate_context_chunks
    from style_summarizer import generate_style_summary
    from context_embedder import generate_embeddings
    
    def generate():
        try:
            # Step 1: Check files are ready
            yield f"data: {json_module.dumps({'step': 'checking', 'progress': 0, 'message': 'Checking files...'})}\n\n"
            
            files = scan_uploads_folder("text")
            if not files:
                yield f"data: {json_module.dumps({'step': 'error', 'progress': 0, 'message': 'No files uploaded'})}\n\n"
                return
            
            # Check all files have subjects
            files_without_subject = [f for f in files if not f.get("subject")]
            if files_without_subject:
                yield f"data: {json_module.dumps({'step': 'error', 'progress': 0, 'message': 'Some files are missing subject selection'})}\n\n"
                return
            
            # Group files by subject
            subject_files = {}
            for f in files:
                subject = f["subject"]
                if subject not in subject_files:
                    subject_files[subject] = []
                subject_files[subject].append(f)
            
            yield f"data: {json_module.dumps({'step': 'preparing', 'progress': 5, 'message': f'Found {len(files)} files for {len(subject_files)} subject(s)'})}\n\n"
            
            # Step 2: Clear preprocessed folder
            yield f"data: {json_module.dumps({'step': 'cleaning', 'progress': 10, 'message': 'Cleaning preprocessed folder...'})}\n\n"
            
            for file_path in PREPROCESSED_DIR.iterdir():
                if file_path.is_file():
                    file_path.unlink()
            
            # Process each subject
            total_subjects = len(subject_files)
            for idx, (subject, subject_file_list) in enumerate(subject_files.items()):
                base_progress = 15 + (idx * 80 // total_subjects)
                step_size = 80 // total_subjects
                
                yield f"data: {json_module.dumps({'step': 'processing', 'progress': base_progress, 'message': f'Processing {subject}...'})}\n\n"
                
                # Prepare file results format: (filename, filepath, filetype, subject)
                file_results = []
                for f in subject_file_list:
                    file_results.append((
                        f["original_name"],
                        f["path"],
                        f["detected_type"],
                        subject
                    ))
                
                # Step 3: Generate style file (temporary)
                yield f"data: {json_module.dumps({'step': 'style', 'progress': base_progress + step_size * 0.15, 'message': f'Generating style data for {subject}...'})}\n\n"
                
                temp_style_path = PREPROCESSED_DIR / f"{subject}_style_temp.txt"
                generate_style_file(file_results, str(temp_style_path))
                
                # Step 4: Generate context chunks
                yield f"data: {json_module.dumps({'step': 'chunks', 'progress': base_progress + step_size * 0.30, 'message': f'Generating context chunks for {subject}...'})}\n\n"
                
                chunks_path = PREPROCESSED_DIR / f"{subject}_context_chunks.json"
                generate_context_chunks(file_results, str(chunks_path))
                
                # Step 5: Generate style summary via Gemini
                yield f"data: {json_module.dumps({'step': 'summary', 'progress': base_progress + step_size * 0.50, 'message': f'Analyzing style with Gemini for {subject}...'})}\n\n"
                
                summary_path = PREPROCESSED_DIR / f"{subject}_style_summary.txt"
                generate_style_summary(str(temp_style_path), str(summary_path), subject)
                
                # Step 6: Generate embeddings
                yield f"data: {json_module.dumps({'step': 'embeddings', 'progress': base_progress + step_size * 0.75, 'message': f'Generating embeddings for {subject}...'})}\n\n"
                
                embeddings_path = PREPROCESSED_DIR / f"{subject}_embeddings.json"
                generate_embeddings(str(chunks_path), str(embeddings_path))
                
                # Step 7: Cleanup temporary files
                if temp_style_path.exists():
                    temp_style_path.unlink()
                
                yield f"data: {json_module.dumps({'step': 'done_subject', 'progress': base_progress + step_size, 'message': f'Completed {subject}'})}\n\n"
            
            # Final cleanup - remove any remaining temp files
            for file_path in PREPROCESSED_DIR.iterdir():
                if '_temp' in file_path.name or '_style.txt' in file_path.name:
                    file_path.unlink()
            
            yield f"data: {json_module.dumps({'step': 'complete', 'progress': 100, 'message': 'Processing complete!'})}\n\n"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json_module.dumps({'step': 'error', 'progress': 0, 'message': f'Error: {str(e)}'})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


# --- Chat / Sessions Endpoints ---

# Chats directory for persistence
CHATS_DIR = Path(__file__).parent / "chats"
CHATS_DIR.mkdir(exist_ok=True)

# In-memory storage for sessions and messages
sessions = {}
messages = {}
chatbots = {}  # PersonaChatbot instances per session


def save_session(session_id):
    """Save a session to disk."""
    if session_id not in sessions:
        return
    
    session_file = CHATS_DIR / f"{session_id}.json"
    import json
    data = {
        "session": sessions[session_id],
        "messages": messages.get(session_id, [])
    }
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def load_sessions():
    """Load all sessions from disk."""
    import json
    for file_path in CHATS_DIR.iterdir():
        if file_path.suffix == '.json' and not file_path.name.startswith('.'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session = data.get("session", {})
                session_id = session.get("id")
                if session_id:
                    sessions[session_id] = session
                    messages[session_id] = data.get("messages", [])
                    
                    # Initialize chatbot if subject available
                    subject = session.get("subject")
                    if subject:
                        initialize_chatbot(session_id, subject)
            except Exception as e:
                print(f"Error loading session from {file_path}: {e}")


def delete_session_file(session_id):
    """Delete a session file from disk."""
    session_file = CHATS_DIR / f"{session_id}.json"
    if session_file.exists():
        session_file.unlink()


def get_available_subjects():
    """Get list of available subjects from preprocessed folder."""
    subjects = []
    if PREPROCESSED_DIR.exists():
        for file_path in PREPROCESSED_DIR.iterdir():
            if file_path.name.endswith('_embeddings.json'):
                subject = file_path.stem.replace('_embeddings', '')
                subjects.append(subject)
    return subjects


def initialize_chatbot(session_id, subject):
    """Initialize a PersonaChatbot for a session."""
    from chatbot import PersonaChatbot
    
    summary_path = PREPROCESSED_DIR / f"{subject}_style_summary.txt"
    embeddings_path = PREPROCESSED_DIR / f"{subject}_embeddings.json"
    
    if not summary_path.exists() or not embeddings_path.exists():
        return None
    
    try:
        chatbot = PersonaChatbot(str(summary_path), str(embeddings_path))
        chatbots[session_id] = chatbot
        return chatbot
    except Exception as e:
        print(f"Failed to initialize chatbot for {subject}: {e}")
        return None


# Load existing sessions on module load
load_sessions()


@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    """Get all sessions."""
    return jsonify({
        "sessions": list(sessions.values())
    })


@app.route("/api/sessions", methods=["POST"])
def create_session():
    """Create a new chat session."""
    import uuid as uuid_module
    data = request.get_json() or {}
    
    # Get available subjects
    available_subjects = get_available_subjects()
    
    session_id = uuid_module.uuid4().hex[:8]
    name = data.get("name", "New Chat")
    
    # If a subject is available, use the first one
    subject = available_subjects[0] if available_subjects else None
    
    session = {
        "id": session_id,
        "name": name,
        "subject": subject,
        "preview": "Start chatting...",
        "created_at": datetime.now().isoformat()
    }
    
    sessions[session_id] = session
    messages[session_id] = []
    
    # Initialize chatbot if subject available
    if subject:
        initialize_chatbot(session_id, subject)
    
    # Save to disk
    save_session(session_id)
    
    return jsonify(session)


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Delete a session."""
    if session_id in sessions:
        del sessions[session_id]
    if session_id in messages:
        del messages[session_id]
    if session_id in chatbots:
        del chatbots[session_id]
    
    # Delete from disk
    delete_session_file(session_id)
    
    return jsonify({"success": True, "deleted_id": session_id})


@app.route("/api/messages/<session_id>", methods=["GET"])
def get_messages(session_id):
    """Get messages for a session."""
    return jsonify({
        "messages": messages.get(session_id, [])
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """Send a message and get AI response."""
    from datetime import datetime
    import uuid as uuid_module
    
    data = request.get_json()
    content = data.get("content", "").strip()
    session_id = data.get("session_id", "default")
    
    if not content:
        return jsonify({"error": "No message content"}), 400
    
    # Ensure session exists
    if session_id not in sessions:
        # Create default session
        available_subjects = get_available_subjects()
        subject = available_subjects[0] if available_subjects else None
        
        sessions[session_id] = {
            "id": session_id,
            "name": "Chat",
            "subject": subject,
            "preview": content[:50],
            "created_at": datetime.now().isoformat()
        }
        messages[session_id] = []
        
        if subject:
            initialize_chatbot(session_id, subject)
    
    # Create user message
    timestamp = datetime.now().strftime("%I:%M %p")
    user_msg = {
        "id": uuid_module.uuid4().hex[:8],
        "role": "user",
        "content": content,
        "timestamp": timestamp
    }
    
    if session_id not in messages:
        messages[session_id] = []
    messages[session_id].append(user_msg)
    
    # Generate AI response
    chatbot = chatbots.get(session_id)
    
    if chatbot:
        try:
            ai_content = chatbot.chat(content)
        except Exception as e:
            print(f"Chatbot error: {e}")
            ai_content = "I'm having trouble processing that. Please try again."
    else:
        # No chatbot available - check if preprocessing is needed
        available_subjects = get_available_subjects()
        if not available_subjects:
            ai_content = "Please upload chat files and run 'Refresh AI Memory' from the Knowledge Base first."
        else:
            # Try to initialize chatbot
            subject = available_subjects[0]
            if initialize_chatbot(session_id, subject):
                try:
                    ai_content = chatbots[session_id].chat(content)
                except Exception as e:
                    ai_content = f"Error: {str(e)}"
            else:
                ai_content = "Failed to initialize the AI. Please check your preprocessed files."
    
    # Split AI response into multiple messages to emulate natural conversation
    # Split on double newlines or single newlines if they look like separate messages
    import re
    
    # Split on newlines but keep it natural
    raw_parts = re.split(r'\n{1,}', ai_content.strip())
    
    # Filter out empty parts and combine very short ones
    parts = []
    for part in raw_parts:
        part = part.strip()
        if part:
            parts.append(part)
    
    # If no parts or single part, use original content
    if not parts:
        parts = [ai_content]
    
    # Create multiple AI messages
    ai_messages = []
    timestamp = datetime.now().strftime("%I:%M %p")
    
    for i, part in enumerate(parts):
        ai_msg = {
            "id": uuid_module.uuid4().hex[:8],
            "role": "assistant",
            "content": part,
            "timestamp": timestamp
        }
        messages[session_id].append(ai_msg)
        ai_messages.append(ai_msg)
    
    # Update session preview with first message
    if session_id in sessions and ai_messages:
        preview_content = ai_messages[0]["content"]
        sessions[session_id]["preview"] = preview_content[:50] + "..." if len(preview_content) > 50 else preview_content
    
    # Save to disk
    save_session(session_id)
    
    return jsonify({
        "user_message": user_msg,
        "ai_message": ai_messages[0] if len(ai_messages) == 1 else ai_messages[0],
        "ai_messages": ai_messages  # Return all messages
    })


@app.route("/api/subjects", methods=["GET"])
def list_subjects():
    """List available subjects from preprocessed folder."""
    return jsonify({
        "subjects": get_available_subjects()
    })


if __name__ == "__main__":
    # Import datetime for chat
    from datetime import datetime
    
    print("Starting NullTale API on http://localhost:5000")
    print(f"Upload directory: {UPLOAD_DIR}")
    print(f"Root .env loaded from: {ROOT_DIR / '.env'}")
    app.run(host="0.0.0.0", port=5000, debug=True)
