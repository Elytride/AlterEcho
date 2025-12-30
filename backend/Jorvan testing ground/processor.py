import json
import re
import os

def classify_file(file_path):
    """
    Classifies a file as 'WhatsApp', 'Instagram', or 'NULL'.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(4096) # Read first 4KB to check format

        # Check for Instagram (JSON format with 'participants' and 'messages')
        content_stripped = content.strip()
        if content_stripped.startswith('{') or content_stripped.startswith('['):
             try:
                # Try parsing the beginning as partial json or just check for keys if text is large
                # Since we read partial, full json load might fail if file is huge, 
                # but valid instagram files from meta export usually start with structure.
                # Let's try to detect keys loosely if it looks like JSON
                if '"participants":' in content and '"messages":' in content:
                    return 'Instagram'
             except:
                 pass

        # Check for WhatsApp (Pattern: Date, Time - Sender: Message)
        # Sample: 25/10/2025, 12:33 cm - ...
        # Regex for WA header: \d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}.* - 
        wa_pattern = r'\d{1,2}/\d{1,2}/\d{2,4},\s\d{1,2}:\d{2}.*-\s'
        if re.search(wa_pattern, content):
            return 'WhatsApp'

        return 'NULL'
    except Exception as e:
        # print(f"Error reading file {file_path}: {e}")
        return 'NULL'

def extract_participants(file_path, file_type):
    """
    Extracts participants based on file type.
    """
    participants = set()
    
    try:
        if file_type == 'Instagram':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'participants' in data:
                    for p in data['participants']:
                        if 'name' in p:
                            participants.add(p['name'])
        
        elif file_type == 'WhatsApp':
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Pattern to catch: "date, time - Sender: "
            # We want to extract 'Sender'
            # Exclude strict system messages if possible, but the prompt says 
            # "Ami is a contact" which is a system message but has a name? 
            # Actually standard WA export: "date, time - Sender: message"
            # And System: "date, time - Messages ... encrypted" (No colon after hyphen usually or fixed text)
            
            msg_pattern = r'\d{1,2}/\d{1,2}/\d{2,4},\s\d{1,2}:\d{2}.*-\s(.*?):'
            
            for line in lines:
                match = re.search(msg_pattern, line)
                if match:
                    sender = match.group(1)
                    participants.add(sender)
                    
    except Exception as e:
        print(f"Error extracting participants from {file_path}: {e}")
        
    return sorted(list(participants))
