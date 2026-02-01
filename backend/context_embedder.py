"""
Context Embedder Module
Generates embeddings for context chunks using Gemini's text-embedding-004 API.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from root folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini - Removed Global Config


def generate_embeddings(chunks_path, output_path, batch_size=100, client=None, model_name="text-embedding-004"):
    """
    Generate embeddings for all context chunks.
    
    Args:
        chunks_path: Path to the context chunks JSON file
        output_path: Path to write the embeddings JSON file
        batch_size: Number of chunks to embed in each API call
        client: Optional genai.Client instance
        model_name: Name of the embedding model to use
    """
    print(f"\n--- Generating Embeddings ---")
    print(f"  Using model: {model_name}")
    
    # Initialize client if not provided
    if not client:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("Error: GEMINI_API_KEY not found")
            return
        client = genai.Client(api_key=api_key)

    # Load chunks
    with open(chunks_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    subject = data.get('subject', 'Unknown')
    
    print(f"  Loaded {len(chunks)} chunks for {subject}")
    
    # Prepare texts for embedding
    # We embed the subject's text + context about the conversation
    texts_to_embed = []
    for chunk in chunks:
        # Create a rich text representation for embedding
        context_text = f"Conversation with {chunk['partner']} on {chunk['date']}:\n{chunk['subject_text']}"
        texts_to_embed.append(context_text)
    
    # Generate embeddings in batches
    all_embeddings = []
    total_batches = (len(texts_to_embed) + batch_size - 1) // batch_size
    
    for i in range(0, len(texts_to_embed), batch_size):
        batch = texts_to_embed[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        
        try:
            result = client.models.embed_content(
                model=model_name,
                contents=batch,
                config=types.EmbedContentConfig(task_type="retrieval_document")
            )
            # Result is EmbedContentResponse, usually has 'embeddings' list of ContentEmbedding
            # Each ContentEmbedding has 'values' (the vector)
            # Check structure: result.embeddings[i].values
            batch_embeddings = [e.values for e in result.embeddings]
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"  Error embedding batch {batch_num}: {e}")
            # Add empty embeddings for failed chunks
            all_embeddings.extend([[] for _ in batch])
    
    # Attach embeddings to chunks
    for i, chunk in enumerate(chunks):
        chunk['embedding'] = all_embeddings[i] if i < len(all_embeddings) else []
    
    # Write to output file
    output_data = {
        'subject': subject,
        'chunks': chunks,
        'embedding_model': model_name,
        'embedding_dimension': len(all_embeddings[0]) if all_embeddings and all_embeddings[0] else 0
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f)
    
    print(f"  Embeddings written to: {output_path}")
    print(f"  Embedding dimension: {output_data['embedding_dimension']}")
    
    return output_data


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        chunks_path = sys.argv[1]
        output_path = chunks_path.replace('_chunks.json', '_embeddings.json')
        generate_embeddings(chunks_path, output_path)
    else:
        print("Usage: python context_embedder.py <chunks_json_path>")
