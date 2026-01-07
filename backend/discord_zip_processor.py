"""
Discord ZIP Processor Module
Handles extraction and parsing of Discord data export ZIP files.
Only processes DM conversations (ignores server channels).
"""

import os
import json
import zipfile
import shutil
from pathlib import Path
from datetime import datetime


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


def find_messages_path(extracted_path):
    """
    Find the Messages folder within the extracted Discord ZIP.
    
    Args:
        extracted_path: Path to extracted ZIP contents
        
    Returns:
        Path to Messages folder or None if not found
    """
    # Try direct path
    messages_path = extracted_path / "messages"
    if messages_path.exists():
        return messages_path
    
    # Try "Messages" with capital M
    messages_path = extracted_path / "Messages"
    if messages_path.exists():
        return messages_path
    
    # Check one level deep (in case ZIP has a root folder)
    for item in extracted_path.iterdir():
        if item.is_dir():
            for sub in ["messages", "Messages"]:
                check_path = item / sub
                if check_path.exists():
                    return check_path
    
    return None


def load_index_json(messages_path):
    """
    Load the index.json file that maps channel IDs to names.
    
    Args:
        messages_path: Path to the Messages folder
        
    Returns:
        Dict mapping channel ID to display name, or empty dict
    """
    index_path = messages_path / "index.json"
    if not index_path.exists():
        return {}
    
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading index.json: {e}")
        return {}


def build_user_id_map(messages_json_path):
    """
    Build a user ID -> username map by scanning messages for Author field.
    This extracts actual usernames from the message data.
    
    Args:
        messages_json_path: Path to messages.json file
        
    Returns:
        Dict mapping user ID (as string) to username
    """
    user_map = {}
    
    if not messages_json_path.exists():
        return user_map
    
    try:
        with open(messages_json_path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        
        for msg in messages:
            author = msg.get('Author')
            if isinstance(author, dict):
                user_id = author.get('ID')
                username = author.get('Username')
                if user_id and username:
                    # Convert ID to string for consistent lookup
                    user_map[str(user_id)] = username
    except Exception as e:
        print(f"Error building user ID map: {e}")
    
    return user_map


def find_dm_conversations(extracted_path):
    """
    Find all DM conversations in the extracted Discord ZIP.
    Only returns DM channels, not server channels.
    
    Args:
        extracted_path: Path to extracted ZIP contents
        
    Returns:
        List of conversation info dicts with:
        - folder_name: Channel folder name (e.g., "c1234567890")
        - display_name: Recipient name from index.json
        - path: Full path to the folder
        - message_count: Number of messages
        - channel_id: Discord channel ID
    """
    messages_path = find_messages_path(extracted_path)
    
    if not messages_path:
        return []
    
    # Load index.json for display names
    index = load_index_json(messages_path)
    
    conversations = []
    
    for folder in messages_path.iterdir():
        if not folder.is_dir():
            continue
        
        # Skip index.json and other non-channel folders
        if not folder.name.startswith('c'):
            continue
        
        # Read channel.json to check if it's a DM
        channel_json = folder / "channel.json"
        if not channel_json.exists():
            continue
        
        try:
            with open(channel_json, 'r', encoding='utf-8') as f:
                channel_data = json.load(f)
            
            # Only include DM channels
            channel_type = channel_data.get('type', '')
            if channel_type != 'DM':
                continue
            
            channel_id = channel_data.get('id', folder.name[1:])  # Remove 'c' prefix
            
            # Get message count
            messages_json = folder / "messages.json"
            message_count = 0
            if messages_json.exists():
                try:
                    with open(messages_json, 'r', encoding='utf-8') as f:
                        messages = json.load(f)
                        message_count = len(messages)
                except:
                    pass
            
            # Get display name from index.json
            display_name = index.get(channel_id, f"DM {channel_id}")
            
            # Clean up display name (remove "Direct Message with " prefix if present)
            if display_name.startswith("Direct Message with "):
                display_name = display_name[20:]
            
            conversations.append({
                "folder_name": folder.name,
                "display_name": display_name,
                "path": str(folder),
                "message_count": message_count,
                "channel_id": channel_id
            })
            
        except Exception as e:
            print(f"Error reading channel {folder.name}: {e}")
            continue
    
    # Sort by message count (most active first)
    conversations.sort(key=lambda x: x["message_count"], reverse=True)
    
    return conversations


def convert_discord_to_instagram_format(folder_path):
    """
    Convert Discord messages.json to Instagram-like JSON format.
    This allows reuse of the existing Instagram parsing pipeline.
    
    Args:
        folder_path: Path to the Discord channel folder
        
    Returns:
        Instagram-format JSON data or None on error
    """
    folder_path = Path(folder_path)
    messages_json = folder_path / "messages.json"
    channel_json = folder_path / "channel.json"
    
    if not messages_json.exists():
        return None
    
    try:
        with open(messages_json, 'r', encoding='utf-8') as f:
            discord_messages = json.load(f)
        
        # Load index for name resolution
        messages_path = folder_path.parent
        index_map = load_index_json(messages_path)
        
        # Build user ID -> username map from messages (for exports with Author field)
        user_id_map = build_user_id_map(messages_json)
        
        # Build participants list
        participants = []
        seen_names = set()
        
        # First, try to get participants from Author fields in messages (newer export format)
        for user_id, username in user_id_map.items():
            if username not in seen_names:
                participants.append({"name": username})
                seen_names.add(username)
        
        # If no participants from messages (older export format without Author field),
        # extract username from index.json using the CHANNEL ID
        if not participants and channel_json.exists():
            with open(channel_json, 'r', encoding='utf-8') as f:
                channel_data = json.load(f)
            
            # Get channel ID and look up in index_map
            channel_id = channel_data.get('id', '')
            if channel_id:
                channel_id_str = str(channel_id)
                display_name = index_map.get(channel_id_str, '')
                
                # Parse username from "Direct Message with username#0" format
                if display_name.startswith("Direct Message with "):
                    username = display_name[20:]  # Remove "Direct Message with " prefix
                    # Remove discriminator if present (e.g., #0, #1234)
                    if '#' in username:
                        username = username.rsplit('#', 1)[0]
                    if username and username not in seen_names:
                        participants.append({"name": username})
                        seen_names.add(username)
                    # Add "Me" as an option for the exporter (since we can't know their username)
                    if "Me" not in seen_names:
                        participants.append({"name": "Me"})
                        seen_names.add("Me")
        
        # Ultimate fallback: use folder name or generic name
        if not participants:
            participants.append({"name": "Discord_User"})
        
        # Convert messages to Instagram format
        instagram_messages = []
        
        for msg in discord_messages:
            # Skip empty messages (usually attachments-only)
            content = msg.get('Contents', '')
            if not content:
                continue
            
            # Parse Discord timestamp (format: "2025-06-16 09:24:12")
            timestamp_str = msg.get('Timestamp', '')
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                timestamp_ms = int(dt.timestamp() * 1000)
            except:
                timestamp_ms = 0
            
            # Try to get sender name
            sender_name = "Unknown"
            if 'Author' in msg:
                author = msg['Author']
                if isinstance(author, dict):
                    # New format: Author is a dict
                    sender_name = author.get('Username', author.get('ID', 'Unknown'))
                    # Try to map ID to display name if logic allows, but usually Username is fine
                else:
                    # Old format: Author might be just ID? Or missing.
                    sender_name = str(author)
            else:
                # Fallback: if we are in a DM, and we don't know who sent it...
                # It's hard. But usually 'Author' is present.
                # If missing, defaulting to one of the participants is risky.
                sender_name = "Discord_User"
            
            instagram_messages.append({
                "sender_name": sender_name,
                "content": content,
                "timestamp_ms": timestamp_ms
            })
        
        # Check if we found actual sender info (not just fallbacks)
        has_sender_info = any(
            msg.get('sender_name') not in ['Unknown', 'Discord_User', None]
            for msg in instagram_messages
        )
        
        # Sort by timestamp (oldest first, matching Instagram format expectation)
        instagram_messages.sort(key=lambda x: x["timestamp_ms"])
        
        # Instagram format has messages in reverse chronological order
        instagram_messages.reverse()
        
        result = {
            "participants": participants if participants else [{"name": "Discord_User"}],
            "messages": instagram_messages,
            "has_sender_info": has_sender_info
        }
        
        # Add warning if export lacks sender info
        if not has_sender_info:
            result["warning"] = (
                "This Discord export uses an older format without sender information. "
                "All messages will appear as 'Discord_User'. For proper AI training, "
                "request a new data export from Discord which includes Author data."
            )
        
        return result
        
    except Exception as e:
        print(f"Error converting Discord messages: {e}")
        return None


def cleanup_zip(zip_id):
    """
    Clean up temporary files for a ZIP extraction.
    
    Args:
        zip_id: The ZIP identifier
    """
    extract_dir = TEMP_ZIP_DIR / zip_id
    if extract_dir.exists():
        shutil.rmtree(extract_dir)


if __name__ == "__main__":
    # Test the module
    import sys
    
    if len(sys.argv) >= 2:
        zip_path = sys.argv[1]
        zip_id = "discord_test"
        
        print(f"Extracting {zip_path}...")
        extracted = extract_zip(zip_path, zip_id)
        print(f"Extracted to: {extracted}")
        
        print("\nFinding DM conversations...")
        conversations = find_dm_conversations(extracted)
        
        for conv in conversations:
            print(f"\n  {conv['display_name']}")
            print(f"    Folder: {conv['folder_name']}")
            print(f"    Messages: {conv['message_count']}")
        
        # Cleanup
        cleanup_zip(zip_id)
        print("\nCleaned up temp files.")
    else:
        print("Usage: python discord_zip_processor.py <zip_file_path>")
