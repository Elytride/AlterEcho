"""
Instagram ZIP Processor Module
Handles extraction and parsing of Instagram data export ZIP files.
"""

import os
import json
import zipfile
import shutil
import tempfile
from pathlib import Path


# Temporary directory for ZIP extraction
TEMP_ZIP_DIR = Path(__file__).parent / "temp_zip"
TEMP_ZIP_DIR.mkdir(exist_ok=True)


def extract_zip(zip_path, zip_id):
    """
    Extract a ZIP file to a temporary directory.
    
    Args:
        zip_path: Path to the ZIP file
        zip_id: Unique identifier for this ZIP (used for temp folder name)
        
    Returns:
        Path to the extracted directory
    """
    extract_dir = TEMP_ZIP_DIR / zip_id
    
    # Clean up if exists
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    
    extract_dir.mkdir(parents=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    
    return extract_dir


def find_inbox_path(extracted_path):
    """
    Find the inbox folder within the extracted ZIP.
    The path structure is: your_instagram_activity/messages/inbox/
    
    Args:
        extracted_path: Path to extracted ZIP contents
        
    Returns:
        Path to inbox folder or None if not found
    """
    # Try common path patterns
    patterns = [
        extracted_path / "your_instagram_activity" / "messages" / "inbox",
        # Sometimes the root folder name varies
    ]
    
    # Also check one level deep in case ZIP has a root folder
    for item in extracted_path.iterdir():
        if item.is_dir():
            patterns.append(item / "your_instagram_activity" / "messages" / "inbox")
            patterns.append(item / "messages" / "inbox")
    
    for pattern in patterns:
        if pattern.exists() and pattern.is_dir():
            return pattern
    
    return None


def find_conversations(extracted_path):
    """
    Find all conversation folders in the extracted ZIP.
    
    Args:
        extracted_path: Path to extracted ZIP contents
        
    Returns:
        List of conversation info dicts with:
        - folder_name: Raw folder name
        - display_name: Cleaned display name
        - path: Full path to the folder
        - participants: List of participant names
        - message_count: Approximate message count
    """
    inbox_path = find_inbox_path(extracted_path)
    
    if not inbox_path:
        return []
    
    conversations = []
    
    for folder in inbox_path.iterdir():
        if not folder.is_dir():
            continue
        
        # Check if this folder contains message files
        message_files = list(folder.glob("message_*.json"))
        if not message_files:
            continue
        
        # Get conversation preview
        preview = get_conversation_preview(folder)
        
        if preview:
            conversations.append({
                "folder_name": folder.name,
                "display_name": preview.get("display_name", folder.name),
                "path": str(folder),
                "participants": preview.get("participants", []),
                "message_count": preview.get("message_count", 0)
            })
    
    # Sort by message count (most active first)
    conversations.sort(key=lambda x: x["message_count"], reverse=True)
    
    return conversations


def get_conversation_preview(folder_path):
    """
    Get preview info for a conversation folder.
    
    Args:
        folder_path: Path to the conversation folder
        
    Returns:
        Dict with display_name, participants, message_count
    """
    folder_path = Path(folder_path)
    message_1 = folder_path / "message_1.json"
    
    if not message_1.exists():
        return None
    
    try:
        with open(message_1, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract participants
        participants = []
        if 'participants' in data:
            for p in data['participants']:
                name = p.get('name', 'Unknown')
                # Fix Instagram's mojibake encoding
                try:
                    name = name.encode('latin-1').decode('utf-8')
                except:
                    pass
                participants.append(name)
        
        # Count messages across all message files
        message_count = 0
        for msg_file in folder_path.glob("message_*.json"):
            try:
                with open(msg_file, 'r', encoding='utf-8') as f:
                    msg_data = json.load(f)
                    message_count += len(msg_data.get('messages', []))
            except:
                pass
        
        # Create display name from participants
        display_name = ", ".join(participants[:2])
        if len(participants) > 2:
            display_name += f" +{len(participants) - 2}"
        
        return {
            "display_name": display_name,
            "participants": participants,
            "message_count": message_count
        }
    
    except Exception as e:
        print(f"Error reading conversation preview: {e}")
        return None


def merge_conversation_messages(folder_path):
    """
    Merge all message_*.json files in a conversation folder into a single JSON object.
    
    Args:
        folder_path: Path to the conversation folder
        
    Returns:
        Combined JSON data with all messages
    """
    folder_path = Path(folder_path)
    
    # Find all message files and sort them (message_1.json has newest, higher numbers have older)
    message_files = sorted(
        folder_path.glob("message_*.json"),
        key=lambda x: int(x.stem.split('_')[1]),
        reverse=True  # Start from highest number (oldest) to lowest (newest)
    )
    
    if not message_files:
        return None
    
    # Start with the first file as base (has participants info)
    first_file = folder_path / "message_1.json"
    if not first_file.exists():
        first_file = message_files[-1]  # Use lowest number file
    
    with open(first_file, 'r', encoding='utf-8') as f:
        combined_data = json.load(f)
    
    # Collect all messages
    all_messages = []
    
    for msg_file in message_files:
        try:
            with open(msg_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages = data.get('messages', [])
                all_messages.extend(messages)
        except Exception as e:
            print(f"Error reading {msg_file}: {e}")
    
    # Sort messages by timestamp (oldest first for consistency)
    all_messages.sort(key=lambda x: x.get('timestamp_ms', 0))
    
    # Update combined data with all messages
    combined_data['messages'] = all_messages
    
    return combined_data


def cleanup_zip(zip_id):
    """
    Clean up temporary files for a ZIP extraction.
    
    Args:
        zip_id: The ZIP identifier
    """
    extract_dir = TEMP_ZIP_DIR / zip_id
    if extract_dir.exists():
        shutil.rmtree(extract_dir)


def cleanup_all_temp():
    """Clean up all temporary ZIP files."""
    if TEMP_ZIP_DIR.exists():
        for item in TEMP_ZIP_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()


if __name__ == "__main__":
    # Test the module
    import sys
    
    if len(sys.argv) >= 2:
        zip_path = sys.argv[1]
        zip_id = "test_extraction"
        
        print(f"Extracting {zip_path}...")
        extracted = extract_zip(zip_path, zip_id)
        print(f"Extracted to: {extracted}")
        
        print("\nFinding conversations...")
        conversations = find_conversations(extracted)
        
        for conv in conversations:
            print(f"\n  {conv['display_name']}")
            print(f"    Folder: {conv['folder_name']}")
            print(f"    Participants: {conv['participants']}")
            print(f"    Messages: {conv['message_count']}")
        
        # Cleanup
        cleanup_zip(zip_id)
        print("\nCleaned up temp files.")
    else:
        print("Usage: python instagram_zip_processor.py <zip_file_path>")
