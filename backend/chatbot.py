"""
Chatbot Module
A persona-based chatbot that combines style, RAG context, and conversation memory.
"""

import os
import json
import uuid
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from context_retriever import ContextRetriever

# Load environment variables from root folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini - Removed Global Config



class PersonaChatbot:
    """
    A chatbot that replicates a person's talking style with RAG-based knowledge.
    """
    
    def __init__(self, style_summary_path, embeddings_path, max_history=10, client=None, model_name="gemini-2.0-flash"):
        """
        Initialize the chatbot.
        
        Args:
            style_summary_path: Path to the style summary txt file
            embeddings_path: Path to the context embeddings JSON file
            max_history: Maximum number of conversation turns to remember
            client: Optional pre-configured genai.Client instance
            model_name: Name of the model to use
        """
        # Load style summary
        with open(style_summary_path, 'r', encoding='utf-8') as f:
            self.style_summary = f.read()
            
        # Initialize client
        if client:
            self.client = client
        else:
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found")
            self.client = genai.Client(api_key=api_key)
            
        self.model_name = model_name
        self.image_model_name = "gemini-2.0-flash" # Default fallback, will be overridden by settings
        
        # Initialize context retriever
        self.retriever = ContextRetriever(embeddings_path, client=self.client)
        self.subject = self.retriever.subject
        
        # Initialize conversation history
        self.conversation_history = []
        self.max_history = max_history
        
        # Image history for context - stores {id, description, source: 'user'|'ai'}
        self.image_history = []
        
        print(f"Chatbot initialized for {self.subject}")
        print(f"  Style summary: {len(self.style_summary):,} characters")
        print(f"  Context chunks: {len(self.retriever.chunks)}")
    
    def set_image_model(self, model_name):
        """Set the model used for image generation calls."""
        self.image_model_name = model_name
        print(f"[DEBUG] Image model set to: {model_name}")

    def _generate_image_tool(self, prompt: str, mode: str = "generate", reference_image_id: str = None):
        """
        Generates or edits an image using Gemini native image generation.
        
        Args:
            prompt: Description of image to generate or edits to make
            mode: 'generate' for new images, 'edit' for modifying existing
            reference_image_id: ID of existing image to edit (used when mode='edit')
        """
        print(f"[DEBUG] TOOL CALL: Image {'Edit' if mode == 'edit' else 'Generate'}")
        print(f"[DEBUG]   Prompt: '{prompt}'")
        print(f"[DEBUG]   Mode: {mode}")
        if reference_image_id:
            print(f"[DEBUG]   Reference Image ID: {reference_image_id}")
        print(f"[DEBUG]   Using image model: {self.image_model_name}")
        
        try:
            serving_model = self.image_model_name
            print(f"[DEBUG]   Resolved to serving model: {serving_model}")
            
            # Build contents for the request
            contents = []
            
            # If editing, find and include the reference image
            if mode == "edit" and reference_image_id:
                ref_image = next((img for img in self.image_history if img['id'] == reference_image_id), None)
                if ref_image and 'pil_image' in ref_image:
                    contents.append(ref_image['pil_image'])
                    contents.append(f"Edit this image: {prompt}")
                else:
                    # Reference not found, generate new instead
                    print(f"[DEBUG]   Reference image not found, generating new")
                    contents.append(prompt)
            else:
                contents.append(prompt)
            
            # Use generate_content per official Google docs
            response = self.client.models.generate_content(
                model=serving_model,
                contents=contents,
            )
            
            # Extract image from response parts
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_bytes = part.inline_data.data
                        
                        # Generate a unique ID for this image
                        img_id = str(uuid.uuid4())[:8]
                        
                        # Store in a temporary list for the current turn
                        if not hasattr(self, '_current_turn_images'):
                            self._current_turn_images = []
                        
                        self._current_turn_images.append({
                            "id": img_id,
                            "bytes": image_bytes,
                            "prompt": prompt
                        })
                        
                        # Add to image history
                        self.image_history.append({
                            "id": img_id,
                            "description": prompt[:100],
                            "source": "ai"
                        })
                        
                        print(f"[DEBUG]   Image generated successfully. ID: {img_id}")
                        return f"Image generated successfully. ID: {img_id}"
            
            print(f"[DEBUG]   No image found in response")
            return "Failed to generate image - no image in response."
            
        except Exception as e:
            print(f"[DEBUG] Image gen error: {e}")
            return f"Error creating image: {str(e)}"

    def _build_system_prompt(self, retrieved_context):
        """
        Build system prompt for TEXT CHAT with optional image generation.
        
        This is SEPARATE from voice prompts. Text chat allows:
        - Emojis and expressive text (hiiiii, !!!, etc.)
        - Image generation and editing
        - Spontaneous image sharing
        
        For voice conversations, use _build_voice_system_prompt() instead.
        """
        # Build image context section
        image_context = ""
        if self.image_history:
            image_lines = []
            for i, img in enumerate(self.image_history[-5:]):  # Last 5 images
                # Mark the most recent image
                is_latest = (i == len(self.image_history[-5:]) - 1)
                marker = " [MOST RECENT]" if is_latest else ""
                image_lines.append(f"  - [{img['id']}]{marker}: {img['description']} (from {img['source']})")
            image_context = f"""## IMAGES IN THIS CHAT
You can reference or edit these images using the generate_or_edit_image tool with mode='edit' and their ID:
{chr(10).join(image_lines)}

IMPORTANT: When the user asks to modify/edit/add to an image without specifying which one, use the MOST RECENT image."""
        
        return f"""You are roleplaying as {self.subject}. Your goal is to respond EXACTLY like {self.subject} would.

## STYLE GUIDE
{self.style_summary}

## RELEVANT MEMORIES
{retrieved_context}

{image_context}

## INSTRUCTIONS
1. Respond ONLY as {self.subject} would.
2. Match energy, tone, and slang.
3. **IMAGES**: You have the ability to generate or edit images using the `generate_or_edit_image` tool.
   - Use `mode: "generate"` to create new images from scratch.
   - Use `mode: "edit"` with a `reference_image_id` to modify an existing image from the chat.
   - **When user asks to edit/modify/add to an image, ALWAYS use mode="edit" with the most recent image's ID.**
   - If the user asks for a picture, drawing, or edit, USE THE TOOL.
   - You MUST also write a text response to accompany any image (e.g., "Check this out!", "Here you go!").
4. **SPONTANEOUS IMAGES**: Based on your personality as {self.subject}, you may OCCASIONALLY share images without being asked:
   - Share when you're excited about something ("omg look at this!!", "I made this for you").
   - Share when something reminds you of the conversation.
   - Share to express emotions visually ("this is how I feel rn").
   - DO NOT share images every message - only when it feels natural and in-character.
   - Think: "Would {self.subject} send a picture here?" - if yes, do it naturally.
5. If you receive an image from the user, react to it naturally based on your persona.
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
    
    def chat(self, user_message, user_image=None, top_k_context=5):
        """
        Send a message and get a response (text + optional images).
        
        Args:
            user_message: The user's text message
            user_image: Optional PIL Image or bytes
            top_k_context: Number of context chunks to retrieve
            
        Returns:
            dict: {
                "text": str,
                "images": list of {id, bytes, prompt}
            }
        """
        # Reset current turn images
        self._current_turn_images = []
        
        # Retrieve relevant context
        retrieved = self.retriever.retrieve(user_message, top_k=top_k_context)
        context_text = self.retriever.format_context(retrieved, include_exchange=True)
        
        # Build prompt
        system_prompt = self._build_system_prompt(context_text)
        history_text = "\n".join(self._build_history_list()) # Helper for text history
        
        # Prepare content for Gemini
        # We need to construct the full request
        
        contents = []
        
        # System Instruction (Implicitly via instructions in first prompt or distinct system_instruction if 2.0 supports it well)
        # We'll stick to prepending for robustness
        
        combined_prompt_text = f"""{system_prompt}

## CONVERSATION HISTORY
{history_text}

## CURRENT MESSAGE
User: {user_message}

Respond as {self.subject}:"""

        prompt_parts = [combined_prompt_text]
        if user_image:
            prompt_parts.append(user_image)
            
        # Dual-purpose tool declaration for generate/edit image
        generate_or_edit_image_declaration = types.FunctionDeclaration(
            name="generate_or_edit_image",
            description="Generate a new image or edit an existing image from the chat. Use mode='generate' for new images, mode='edit' for modifying existing images.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description="A detailed description of the image to generate, or description of the edits to make."
                    ),
                    "mode": types.Schema(
                        type=types.Type.STRING,
                        description="Either 'generate' for new images or 'edit' for modifying existing images."
                    ),
                    "reference_image_id": types.Schema(
                        type=types.Type.STRING,
                        description="Optional. The ID of an existing image from the chat to edit (only used when mode='edit')."
                    )
                },
                required=["prompt", "mode"]
            )
        )
        
        tools = types.Tool(function_declarations=[generate_or_edit_image_declaration])
        
        print(f"[DEBUG] Chat using model: {self.model_name}")
        print(f"[DEBUG] Chat image model configured: {self.image_model_name}")
        
        try:
            # First turn: Send prompt + (optional) image
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_parts,
                config=types.GenerateContentConfig(
                    tools=[tools],
                )
            )
            
            # Manual Function Calling Loop
            assistant_message = ""
            max_iterations = 3
            current_contents = list(prompt_parts) # Start with initial prompt
            
            for _ in range(max_iterations):
                # Check if model wants to call a function
                if response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        print(f"Function Call Detected: {fc.name}")
                        
                        if fc.name == "generate_or_edit_image":
                            prompt_arg = fc.args.get("prompt", "")
                            mode_arg = fc.args.get("mode", "generate")
                            ref_id_arg = fc.args.get("reference_image_id", None)
                            tool_result = self._generate_image_tool(prompt_arg, mode_arg, ref_id_arg)
                            
                            # Add the model's function call turn
                            current_contents.append(response.candidates[0].content)
                            
                            # Add the function response
                            function_response_part = types.Part.from_function_response(
                                name="generate_or_edit_image",
                                response={"result": tool_result}
                            )
                            current_contents.append(types.Content(parts=[function_response_part], role="user"))
                            
                            # Continue the conversation
                            response = self.client.models.generate_content(
                                model=self.model_name,
                                contents=current_contents,
                                config=types.GenerateContentConfig(
                                    tools=[tools],
                                )
                            )
                            continue
                    
                    # If no function call, extract text
                    if hasattr(part, 'text') and part.text:
                        assistant_message = part.text.strip()
                        break
                else:
                    # Fallback
                    if response.text:
                        assistant_message = response.text.strip()
                    break
            
            # Clean up
            if assistant_message.startswith(f"{self.subject}:"):
                assistant_message = assistant_message[len(f"{self.subject}:"):].strip()
            
            # Update history (Text only for now)
            self.conversation_history.append({
                'user': user_message,
                'assistant': assistant_message
            })
            
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]
            
            return {
                "text": assistant_message,
                "images": self._current_turn_images
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Chat Error: {e}")
            return {
                "text": f"Error: {e}",
                "images": []
            }

    def _build_history_list(self):
        if not self.conversation_history:
            return []
        formatted = []
        for turn in self.conversation_history[-self.max_history:]:
            formatted.append(f"User: {turn['user']}")
            formatted.append(f"{self.subject}: {turn['assistant']}")
        return formatted

    def _clean_for_tts(self, text):
        """
        Clean text for TTS output - remove patterns that cause issues.
        """
        import re
        
        # Remove ellipsis (... or more dots)
        text = re.sub(r'\.{2,}', '.', text)
        
        # Remove multiple exclamation/question marks
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        
        # Remove asterisk actions like *laughs*
        text = re.sub(r'\*[^*]+\*', '', text)
        
        # Remove emoji (common unicode ranges)
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
        
        # Clean up repeated letters (hiiiii -> hi, but keep double letters like "hello")
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)  # Keep at most 2 repeated chars
        
        # Clean up any resulting double spaces
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()
    def _build_voice_system_prompt(self, retrieved_context):
        """
        Build a voice-optimized system prompt for TTS output.
        This is SEPARATE from the chat prompt - optimized specifically for spoken audio.
        """
        return f"""You are having a VOICE CONVERSATION as {self.subject}. Your responses will be read aloud by a text-to-speech system.

## PERSONALITY REFERENCE
{self.style_summary}

## RELEVANT MEMORIES
{retrieved_context}

## CRITICAL TTS RULES (MUST FOLLOW)
Your response will be spoken by TTS. You MUST:

1. **NO elongated words**: Never write "hiiiii", "sooooo", "nooooo", "yesssss", etc. Write normally: "hi", "so", "no", "yes"
2. **NO multiple punctuation**: Never write "!!!", "???", or "..." (ellipsis). Use single punctuation only.
3. **NO trailing dots**: End sentences cleanly. Never trail off with "...." or "..."
4. **NO emojis or special characters**: They will be read literally and sound terrible.
5. **NO asterisks for actions**: Never write *laughs* or *sighs*. Express emotions through words.
6. **NO ALL CAPS**: TTS handles this poorly. Use words like "really" or "so" for emphasis.
7. **Standard spelling only**: Write "you" not "u", "are" not "r", "okay" not "okkkk"

## RESPONSE STYLE
- Speak naturally as {self.subject} would in a phone call
- Keep responses conversational and flowing
- Be engaging but concise (2-4 sentences typically)
- Match their personality but make it speakable

Respond as {self.subject}:"""

    def stream_chat_voice(self, user_message, top_k_context=5):
        """
        Stream text response for voice output.
        This is optimized for voice - no image generation, just text streaming.
        
        Yields:
            Text chunks from the model response.
        """
        print(f"[VOICE DEBUG] stream_chat_voice called with: '{user_message[:50]}...'")
        
        try:
            # Retrieve relevant context
            retrieved = self.retriever.retrieve(user_message, top_k=top_k_context)
            context_text = self.retriever.format_context(retrieved, include_exchange=True)
            
            # Build voice-optimized prompt
            system_prompt = self._build_voice_system_prompt(context_text)
            history_text = "\n".join(self._build_history_list())
            
            combined_prompt_text = f"""{system_prompt}

## CONVERSATION HISTORY
{history_text}

## CURRENT MESSAGE
User: {user_message}

Respond as {self.subject}:"""

            print(f"[VOICE DEBUG] Sending to Gemini model: {self.model_name}")
            
            # Use streaming for voice response
            response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=combined_prompt_text,
            )
            
            full_response = ""
            chunk_count = 0
            
            for chunk in response:
                if chunk.text:
                    chunk_count += 1
                    # Clean text for TTS
                    clean_text = self._clean_for_tts(chunk.text)
                    if chunk_count == 1:
                        print(f"[VOICE DEBUG] First chunk received: '{clean_text[:30]}...'")
                    full_response += clean_text
                    if clean_text:  # Only yield if there's content after cleaning
                        yield clean_text
            
            print(f"[VOICE DEBUG] Stream complete. Total chunks: {chunk_count}, Response length: {len(full_response)}")
            
            # Update conversation history
            if full_response.strip():
                # Clean up response
                clean_response = full_response.strip()
                if clean_response.startswith(f"{self.subject}:"):
                    clean_response = clean_response[len(f"{self.subject}:"):].strip()
                
                self.conversation_history.append({
                    'user': user_message,
                    'assistant': clean_response
                })
                
                if len(self.conversation_history) > self.max_history:
                    self.conversation_history = self.conversation_history[-self.max_history:]
                    
        except Exception as e:
            print(f"[VOICE DEBUG] stream_chat_voice error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            yield f"Sorry, I had trouble responding. Error: {str(e)}"

    # Old stream_chat kept as stub for compatibility
    def stream_chat(self, *args, **kwargs):
        print("[VOICE DEBUG] stream_chat STUB called - use stream_chat_voice instead")
        return []

    
    def reset_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        print("Conversation history cleared.")
    
    def get_history(self):
        """Get the current conversation history."""
        return self.conversation_history.copy()

import uuid # Needed for ID generation

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
