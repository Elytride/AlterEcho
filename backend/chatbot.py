"""
Chatbot Module
A persona-based chatbot that combines style, RAG context, and conversation memory.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from context_retriever import ContextRetriever

# Load environment variables from root folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))


class PersonaChatbot:
    """
    A chatbot that replicates a person's talking style with RAG-based knowledge.
    """
    
    def __init__(self, style_summary_path, embeddings_path, max_history=10, model=None):
        """
        Initialize the chatbot.
        
        Args:
            style_summary_path: Path to the style summary txt file
            embeddings_path: Path to the context embeddings JSON file
            max_history: Maximum number of conversation turns to remember
            model: Optional pre-configured Gemini model instance
        """
        # Load style summary
        with open(style_summary_path, 'r', encoding='utf-8') as f:
            self.style_summary = f.read()
        
        # Initialize context retriever
        self.retriever = ContextRetriever(embeddings_path)
        self.subject = self.retriever.subject
        
        # Initialize conversation history
        self.conversation_history = []
        self.max_history = max_history
        
        # Initialize Gemini model
        if model:
            self.model = model
        else:
            self.model = genai.GenerativeModel('gemini-flash-latest')
        
        print(f"Chatbot initialized for {self.subject}")
        print(f"  Style summary: {len(self.style_summary):,} characters")
        print(f"  Context chunks: {len(self.retriever.chunks)}")
    
    def _build_system_prompt(self, retrieved_context):
        """
        Build the system prompt combining style and context.
        """
        return f"""You are roleplaying as {self.subject}. Your goal is to respond EXACTLY like {self.subject} would, matching their personality, vocabulary, tone, and mannerisms perfectly.

## STYLE GUIDE
The following is a detailed analysis of {self.subject}'s communication style. You MUST follow this guide precisely:

{self.style_summary}

---

## RELEVANT MEMORIES/CONTEXT
The following are real conversations {self.subject} has had that may be relevant to the current topic. Use these to inform your responses with accurate knowledge and context:

{retrieved_context}

---

## INSTRUCTIONS
1. Respond ONLY as {self.subject} would - use their exact vocabulary, slang, emoji patterns, and message style
2. Match the energy level and tone from the style guide
3. Use the retrieved context to answer questions accurately based on what {self.subject} actually knows or has said
4. If the context doesn't contain relevant information, respond naturally as {self.subject} would when they don't know something
5. NEVER break character or acknowledge that you are an AI
6. Keep messages short and natural - {self.subject} sends multiple short messages, not long paragraphs
7. Use appropriate humor and sarcasm as documented in the style guide
"""
    
    def _format_history(self):
        """
        Format conversation history for the prompt.
        """
        if not self.conversation_history:
            return ""
        
        formatted = []
        for turn in self.conversation_history[-self.max_history:]:
            formatted.append(f"User: {turn['user']}")
            formatted.append(f"{self.subject}: {turn['assistant']}")
        
        return "\n".join(formatted)
    
    def chat(self, user_message, top_k_context=5):
        """
        Send a message and get a response.
        
        Args:
            user_message: The user's message
            top_k_context: Number of context chunks to retrieve
            
        Returns:
            The chatbot's response
        """
        # Retrieve relevant context
        retrieved = self.retriever.retrieve(user_message, top_k=top_k_context)
        context_text = self.retriever.format_context(retrieved, include_exchange=True)
        
        # Build the full prompt
        system_prompt = self._build_system_prompt(context_text)
        history_text = self._format_history()
        
        # Construct the conversation for Gemini
        full_prompt = f"""{system_prompt}

## CONVERSATION HISTORY
{history_text}

## CURRENT MESSAGE
User: {user_message}

Respond as {self.subject}:"""
        
        try:
            response = self.model.generate_content(full_prompt)
            assistant_message = response.text.strip()
            
            # Clean up the response (remove any accidental prefixes)
            if assistant_message.startswith(f"{self.subject}:"):
                assistant_message = assistant_message[len(f"{self.subject}:"):].strip()
            
            # Update conversation history
            self.conversation_history.append({
                'user': user_message,
                'assistant': assistant_message
            })
            
            # Trim history if needed
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]
            
            return assistant_message
            
        except Exception as e:
            return f"Error generating response: {e}"
    
    def reset_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        print("Conversation history cleared.")
    
    def get_history(self):
        """Get the current conversation history."""
        return self.conversation_history.copy()


def load_chatbot(subject_name, preprocessed_folder='preprocessed'):
    """
    Convenience function to load a chatbot for a subject.
    
    Args:
        subject_name: Name of the subject
        preprocessed_folder: Path to preprocessed folder
        
    Returns:
        PersonaChatbot instance
    """
    style_path = os.path.join(preprocessed_folder, 'style', f'{subject_name}_style_summary.txt')
    embeddings_path = os.path.join(preprocessed_folder, 'context', f'{subject_name}_context_embeddings.json')
    
    return PersonaChatbot(style_path, embeddings_path)


def interactive_chat(chatbot):
    """
    Run an interactive chat session in the terminal.
    
    Args:
        chatbot: PersonaChatbot instance
    """
    print(f"\n{'='*50}")
    print(f"Chatting with {chatbot.subject}")
    print(f"Type 'quit' to exit, 'reset' to clear history")
    print(f"{'='*50}\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'quit':
                print("Goodbye!")
                break
            
            if user_input.lower() == 'reset':
                chatbot.reset_history()
                continue
            
            response = chatbot.chat(user_input)
            print(f"\n{chatbot.subject}: {response}\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 2:
        subject_name = sys.argv[1]
        chatbot = load_chatbot(subject_name)
        interactive_chat(chatbot)
    else:
        print("Usage: python chatbot.py <subject_name>")
        print("Example: python chatbot.py Jorvan")
