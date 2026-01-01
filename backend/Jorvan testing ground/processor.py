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

# ============== Stage 2: Data Preprocessing Functions ==============

from datetime import datetime, timedelta

def parse_instagram_messages(file_path):
    """
    Parse Instagram JSON file and return list of (datetime, sender, content) tuples.
    Messages are returned in chronological order (oldest first).
    """
    messages = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'messages' in data:
            for msg in data['messages']:
                if 'content' not in msg:
                    continue  # Skip messages without text content (e.g., photos only)
                
                sender = msg.get('sender_name', 'Unknown')
                content = msg['content']
                timestamp_ms = msg.get('timestamp_ms', 0)
                dt = datetime.fromtimestamp(timestamp_ms / 1000)
                
                # Fix Instagram's mojibake encoding for emojis
                try:
                    content = content.encode('latin-1').decode('utf-8')
                except:
                    pass
                try:
                    sender = sender.encode('latin-1').decode('utf-8')
                except:
                    pass
                
                messages.append((dt, sender, content))
        
        # Instagram messages are usually newest first, reverse to get chronological
        messages.reverse()
    except Exception as e:
        print(f"Error parsing Instagram file {file_path}: {e}")
    
    return messages

def parse_whatsapp_messages(file_path):
    """
    Parse WhatsApp .txt file and return list of (datetime, sender, content) tuples.
    Messages are returned in chronological order (oldest first).
    """
    messages = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Pattern: DD/MM/YYYY, HH:MM am/pm - Sender: Message
        msg_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}\s*[ap]m)\s-\s(.*?):\s(.*)$'
        
        current_msg = None
        
        for line in lines:
            match = re.match(msg_pattern, line, re.IGNORECASE)
            if match:
                # Save previous message if exists
                if current_msg:
                    messages.append(current_msg)
                
                date_str = match.group(1)
                time_str = match.group(2)
                sender = match.group(3)
                content = match.group(4)
                
                # Parse datetime
                try:
                    dt_str = f"{date_str} {time_str}"
                    dt = datetime.strptime(dt_str, "%d/%m/%Y %I:%M %p")
                except:
                    try:
                        dt = datetime.strptime(dt_str, "%d/%m/%y %I:%M %p")
                    except:
                        dt = datetime.now()
                
                current_msg = (dt, sender.strip(), content.strip())
            elif current_msg:
                # Continuation of previous message (multi-line)
                dt, sender, content = current_msg
                current_msg = (dt, sender, content + '\n' + line.strip())
        
        # Don't forget the last message
        if current_msg:
            messages.append(current_msg)
            
    except Exception as e:
        print(f"Error parsing WhatsApp file {file_path}: {e}")
    
    return messages

def filter_messages_by_months(messages, months=3):
    """
    Filter messages to only include the last N months from the most recent message.
    """
    if not messages:
        return []
    
    # Find the most recent message timestamp
    most_recent = max(msg[0] for msg in messages)
    cutoff_date = most_recent - timedelta(days=months * 30)
    
    return [msg for msg in messages if msg[0] >= cutoff_date]

def generate_style_file(file_results, output_path, max_lines_per_file=5000):
    """
    Generate style training file.
    - Includes ALL participants' messages (for conversation context)
    - Takes at most max_lines_per_file from each file (most recent)
    - Removes timestamps
    - Separates different source files with dividers
    
    Args:
        file_results: list of (filename, filepath, filetype, subject) tuples
        output_path: path to write output file
        max_lines_per_file: maximum number of messages to take from each file
    """
    all_sections = []
    total_lines = 0
    
    for filename, filepath, filetype, subject in file_results:
        if filetype == 'Instagram':
            messages = parse_instagram_messages(filepath)
        elif filetype == 'WhatsApp':
            messages = parse_whatsapp_messages(filepath)
        else:
            continue
        
        if not messages:
            continue
        
        # Sort by timestamp (oldest first) and take the most recent N messages
        messages.sort(key=lambda x: x[0])
        messages = messages[-max_lines_per_file:]  # Take last N (most recent)
        
        # Format messages
        formatted = []
        for dt, sender, content in messages:
            if content.strip() and content != '<Media omitted>':
                # Replace links with placeholder
                content = re.sub(r'https?://\S+', '*link*', content)
                # Replace very long texts with placeholder
                if len(content) > 700:
                    content = '*long text*'
                formatted.append(f"{sender}: {content}")
        
        if formatted:
            all_sections.append('\n'.join(formatted))
            print(f"  {filename}: {len(formatted)} lines")
            total_lines += len(formatted)
    
    # Write to file with separators
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n--------------------------------------\n'.join(all_sections))
    
    print(f"Style file written to: {output_path} ({total_lines} total lines)")

# Filler words to exclude from context (case-insensitive exact matches)
CONTEXT_FILLER_WORDS = {
    'ok', 'yes', 'no', 'okok', 'lmao', 'lol', 'ah', 'oh', 'ou', 
    'yep', 'idk', 'mhm', 'ight', 'aight', 'thx', 'hi', 'ty', 'hii', 
    'hiii', 'lmaoo', 'k'
}

def is_emoji_only(text):
    """
    Check if text contains only emojis (and whitespace).
    """
    import unicodedata
    stripped = text.strip()
    if not stripped:
        return True
    for char in stripped:
        # Skip whitespace
        if char.isspace():
            continue
        # Check if character is an emoji or symbol
        category = unicodedata.category(char)
        # Emoji categories: So (Symbol, Other), Sk (Symbol, Modifier), Sm (Symbol, Math)
        # Also check for variation selectors and skin tone modifiers
        if category not in ('So', 'Sk', 'Sm', 'Mn', 'Cf') and ord(char) < 0x1F300:
            return False
    return True

def contains_link(text):
    """
    Check if text contains a URL/link.
    """
    import re
    url_pattern = r'https?://|www\.|\.(com|org|net|io|gov|edu|co)(/|\s|$)'
    return bool(re.search(url_pattern, text, re.IGNORECASE))

def generate_context_file(file_results, output_path):
    """
    Generate context file.
    - Includes ONLY subject's messages
    - Includes ALL time (no date filter)
    - Removes timestamps AND sender names
    - Filters out: links, emoji-only messages, and filler words
    
    Args:
        file_results: list of (filename, filepath, filetype, subject) tuples
        output_path: path to write output file
    """
    all_messages = []
    filtered_count = 0
    
    for filename, filepath, filetype, subject in file_results:
        # Parse messages based on file type
        if filetype == 'Instagram':
            messages = parse_instagram_messages(filepath)
        elif filetype == 'WhatsApp':
            messages = parse_whatsapp_messages(filepath)
        else:
            continue
        
        # Filter to only subject's messages
        for dt, sender, content in messages:
            if sender != subject:
                continue
            
            content = content.strip()
            
            # Skip empty or media-only
            if not content or content == '<Media omitted>':
                filtered_count += 1
                continue
            
            # Skip messages with links
            if contains_link(content):
                filtered_count += 1
                continue
            
            # Skip emoji-only messages
            if is_emoji_only(content):
                filtered_count += 1
                continue
            
            # Skip filler words (case-insensitive exact match)
            if content.lower() in CONTEXT_FILLER_WORDS:
                filtered_count += 1
                continue
            
            all_messages.append(content)
    
    # Write to file (just message content, one per line)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_messages))
    
    print(f"Context file written to: {output_path} ({len(all_messages)} messages, {filtered_count} filtered out)")


# ============== Stage 3: Context Chunking for RAG ==============

import json as json_module

def generate_context_chunks(file_results, output_path, chunk_minutes=30):
    """
    Generate enriched context chunks for RAG system.
    Groups messages into conversation blocks based on time windows.
    
    Args:
        file_results: list of (filename, filepath, filetype, subject) tuples
        output_path: path to write JSON output
        chunk_minutes: time window for grouping messages (default 30 mins)
    """
    all_chunks = []
    chunk_id = 0
    
    for filename, filepath, filetype, subject in file_results:
        # Parse messages based on file type
        if filetype == 'Instagram':
            messages = parse_instagram_messages(filepath)
        elif filetype == 'WhatsApp':
            messages = parse_whatsapp_messages(filepath)
        else:
            continue
        
        if not messages:
            continue
        
        # Sort by timestamp
        messages.sort(key=lambda x: x[0])
        
        # Find conversation partners (everyone except the subject)
        partners = set(msg[1] for msg in messages if msg[1] != subject)
        partner_name = ', '.join(partners) if partners else 'Unknown'
        
        # Group messages into time-based chunks
        current_chunk = None
        chunk_window = timedelta(minutes=chunk_minutes)
        
        for dt, sender, content in messages:
            # Skip empty or media-only
            if not content.strip() or content == '<Media omitted>':
                continue
            
            # Check if we need to start a new chunk
            if current_chunk is None or (dt - current_chunk['end_time']) > chunk_window:
                # Save previous chunk if exists
                if current_chunk is not None and current_chunk['messages']:
                    # Only save if subject participated
                    if any(m['sender'] == subject for m in current_chunk['messages']):
                        all_chunks.append(finalize_chunk(current_chunk, subject, chunk_id))
                        chunk_id += 1
                
                # Start new chunk
                current_chunk = {
                    'start_time': dt,
                    'end_time': dt,
                    'source_file': filename,
                    'partner': partner_name,
                    'messages': []
                }
            
            # Add message to current chunk
            current_chunk['messages'].append({
                'sender': sender,
                'text': content,
                'timestamp': dt.isoformat()
            })
            current_chunk['end_time'] = dt
        
        # Don't forget the last chunk
        if current_chunk is not None and current_chunk['messages']:
            if any(m['sender'] == subject for m in current_chunk['messages']):
                all_chunks.append(finalize_chunk(current_chunk, subject, chunk_id))
                chunk_id += 1
    
    # Write to JSON file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json_module.dump({'chunks': all_chunks, 'subject': file_results[0][3] if file_results else 'Unknown'}, f, indent=2)
    
    print(f"Context chunks written to: {output_path} ({len(all_chunks)} chunks)")
    return all_chunks


def finalize_chunk(chunk_data, subject, chunk_id):
    """
    Finalize a chunk by extracting subject messages and creating summary text.
    """
    subject_messages = [m['text'] for m in chunk_data['messages'] if m['sender'] == subject]
    
    # Create a searchable text representation
    full_exchange_text = '\n'.join([f"{m['sender']}: {m['text']}" for m in chunk_data['messages']])
    subject_text = '\n'.join(subject_messages)
    
    return {
        'id': f"chunk_{chunk_id:04d}",
        'date': chunk_data['start_time'].strftime('%Y-%m-%d'),
        'time_range': f"{chunk_data['start_time'].strftime('%H:%M')}-{chunk_data['end_time'].strftime('%H:%M')}",
        'source_file': chunk_data['source_file'],
        'partner': chunk_data['partner'],
        'subject_messages': subject_messages,
        'subject_text': subject_text,  # For embedding
        'full_exchange': chunk_data['messages'],
        'message_count': len(chunk_data['messages'])
    }
