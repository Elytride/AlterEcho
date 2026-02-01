"""
Context Retriever Module
Retrieves relevant context chunks using cosine similarity.
"""

import os
import json
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from root folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini - Removed Global Config


def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


class ContextRetriever:
    """
    Retrieves relevant context chunks based on semantic similarity.
    """
    
    def __init__(self, embeddings_path, client=None):
        """
        Initialize the retriever with pre-computed embeddings.
        
        Args:
            embeddings_path: Path to the embeddings JSON file
            client: Optional genai.Client instance
        """
        if client:
            self.client = client
        else:
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found")
            self.client = genai.Client(api_key=api_key)
            
        with open(embeddings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.subject = data.get('subject', 'Unknown')
        self.chunks = data['chunks']
        self.embedding_model = data.get('embedding_model', 'text-embedding-004')
        
        # Pre-compute numpy arrays for faster retrieval
        self.embeddings = []
        self.valid_indices = []
        
        for i, chunk in enumerate(self.chunks):
            if chunk.get('embedding') and len(chunk['embedding']) > 0:
                self.embeddings.append(np.array(chunk['embedding']))
                self.valid_indices.append(i)
        
        print(f"Loaded {len(self.valid_indices)} embedded chunks for {self.subject}")
    
    def embed_query(self, query):
        """
        Embed a user query using the same embedding model.
        
        Args:
            query: User's query text
            
        Returns:
            Embedding vector
        """
        result = self.client.models.embed_content(
            model="text-embedding-004",
            contents=query,
            config=types.EmbedContentConfig(task_type="retrieval_query")
        )
        return np.array(result.embeddings[0].values)
    
    def retrieve(self, query, top_k=5):
        """
        Retrieve the top-K most relevant chunks for a query.
        
        Args:
            query: User's query text
            top_k: Number of chunks to retrieve
            
        Returns:
            List of (chunk, similarity_score) tuples
        """
        if not self.embeddings:
            return []
        
        # Embed the query
        query_embedding = self.embed_query(query)
        
        # Calculate similarities
        similarities = []
        for i, embedding in enumerate(self.embeddings):
            sim = cosine_similarity(query_embedding, embedding)
            similarities.append((self.valid_indices[i], sim))
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Return top-K chunks with scores
        results = []
        for idx, score in similarities[:top_k]:
            chunk = self.chunks[idx].copy()
            # Remove embedding from result to save memory
            chunk.pop('embedding', None)
            results.append((chunk, score))
        
        return results
    
    def format_context(self, retrieved_chunks, include_exchange=False):
        """
        Format retrieved chunks into a context string for the chatbot.
        
        Args:
            retrieved_chunks: List of (chunk, score) tuples from retrieve()
            include_exchange: Whether to include the full exchange or just subject messages
            
        Returns:
            Formatted context string
        """
        if not retrieved_chunks:
            return "No relevant context found."
        
        context_parts = []
        for chunk, score in retrieved_chunks:
            header = f"[From conversation with {chunk['partner']} on {chunk['date']}]"
            
            if include_exchange:
                messages = '\n'.join([f"{m['sender']}: {m['text']}" for m in chunk['full_exchange'][-10:]])  # Last 10 messages
            else:
                messages = '\n'.join(chunk['subject_messages'][-5:])  # Last 5 subject messages
            
            context_parts.append(f"{header}\n{messages}")
        
        return '\n\n---\n\n'.join(context_parts)


def load_retriever(embeddings_path):
    """
    Convenience function to load a retriever.
    
    Args:
        embeddings_path: Path to embeddings JSON file
        
    Returns:
        ContextRetriever instance
    """
    return ContextRetriever(embeddings_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        embeddings_path = sys.argv[1]
        query = sys.argv[2]
        
        retriever = ContextRetriever(embeddings_path)
        results = retriever.retrieve(query, top_k=3)
        
        print(f"\nTop 3 results for: '{query}'\n")
        for chunk, score in results:
            print(f"[Score: {score:.4f}] {chunk['date']} with {chunk['partner']}")
            print(f"  {chunk['subject_messages'][0][:100]}...")
            print()
    else:
        print("Usage: python context_retriever.py <embeddings_json_path> <query>")
