"""
Style Summarizer Module
Generates an extremely detailed style analysis using Gemini,
plus includes examples from the original style file.
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from root folder
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configure Gemini - Removed Global Config

# Approximate tokens per character (rough heuristic)
CHARS_PER_TOKEN = 4
TARGET_MAX_TOKENS = 100000
MIN_EXAMPLE_PERCENTAGE = 0.20  # Minimum 20% of original
ANALYSIS_TOKEN_BUDGET = 8000   # Reserve tokens for the generated analysis

STYLE_ANALYSIS_PROMPT = """You are an expert linguistic analyst. Analyze the following chat messages from a person named "{subject_name}" and create an EXTREMELY detailed style guide that would allow an AI to perfectly replicate their writing style.

The chat data contains messages from multiple participants, but focus ONLY on analyzing {subject_name}'s messages.

Provide your analysis in the following format:

# Style Analysis: {subject_name}

## Vocabulary & Slang Dictionary
List ALL unique slang, abbreviations, and informal words they use. Include:
- The word/phrase
- What it means
- Example usage from the data
Be exhaustive - list at least 30-50 items if present.

## Tone & Energy Profile
- Default emotional state (e.g., energetic, chill, sarcastic)
- How they express excitement
- How they express frustration/annoyance
- How they express agreement/disagreement
- Use of caps lock patterns
- Punctuation habits (or lack thereof)

## Humor & Sarcasm Patterns
IMPORTANT: Many words/phrases may be used ironically or sarcastically. Analyze:
- Words they use sarcastically vs literally (e.g., "slay", "bestie", "queen" used mockingly by guys)
- How they signal sarcasm (tone shift, emojis, context)
- Types of jokes they make (self-deprecating, teasing, absurdist, dark humor)
- Inside jokes or recurring comedic references
- How they react to others' jokes
- Mocking or parody of internet/gen-z speak (if applicable)

## Sentence Structure Patterns
- Average message length (short bursts vs paragraphs)
- Do they send multiple messages or combine into one?
- How do they start messages?
- How do they end messages?
- Use of line breaks

## Emoji Usage
Create a table with columns: Emoji | Frequency (High/Medium/Low) | Typical Context
List ALL emojis they use.

## Conversational Habits
- Do they ask questions often?
- How do they respond to questions?
- Do they use filler words? Which ones?
- How do they change topics?
- Do they reference previous conversations?

## Response Patterns by Message Type
Analyze how {subject_name} responds differently to various types of incoming messages:
- How do they respond to **compliments**?
- How do they respond to **teasing/roasting**?
- How do they respond to **serious/emotional topics**?
- How do they respond to **questions about themselves**?
- How do they respond to **gossip or drama**?
- How do they respond to **requests for help/advice**?
- How do they respond to **boring/dry messages**?
- How do they respond to **hype/excitement from others**?

## Relationship Dynamics
Based on the conversation patterns, analyze how {subject_name}'s style changes based on who they're talking to:
- What level of closeness/intimacy is shown? (casual friend, close friend, romantic interest, etc.)
- Do they adjust formality based on the conversation partner?
- Are there protective/caring behaviors shown?
- How do they handle disagreements or tension?
- Do they initiate conversations or mostly respond?
- How much do they share about themselves vs ask about others?

## Spelling & Grammar Tendencies
- Intentional misspellings or stylistic choices
- Common typos
- Grammar patterns (fragments, run-ons, etc.)
- Capitalization habits

## Unique Phrases & Catchphrases
List any recurring phrases, expressions, or verbal tics unique to this person.

## Message Timing & Editing
- Do they react to messages before responding?
- Do they edit messages? (look for "(edited)" markers)
- Do they send rapid-fire messages or more measured responses?

---

CHAT DATA:
{chat_data}
"""


def estimate_tokens(text):
    """Estimate token count based on character length."""
    return len(text) // CHARS_PER_TOKEN


def parse_style_sections(style_content):
    """
    Parse the style file into sections separated by dividers.
    Returns list of (section_index, content) tuples.
    """
    divider = '--------------------------------------'
    sections = style_content.split(divider)
    return [(i, section.strip()) for i, section in enumerate(sections) if section.strip()]


def calculate_example_percentage(style_content, analysis_tokens=ANALYSIS_TOKEN_BUDGET):
    """
    Calculate what percentage of the original style file can be included
    while staying under the target token limit.
    """
    style_tokens = estimate_tokens(style_content)
    available_for_examples = TARGET_MAX_TOKENS - analysis_tokens
    
    if style_tokens <= available_for_examples:
        return 1.0  # Include 100%
    
    percentage = available_for_examples / style_tokens
    
    # Enforce minimum 20%
    return max(percentage, MIN_EXAMPLE_PERCENTAGE)


def truncate_section(section_content, percentage):
    """
    Truncate a section to the specified percentage, keeping from the end (most recent).
    """
    lines = section_content.split('\n')
    keep_count = max(1, int(len(lines) * percentage))
    return '\n'.join(lines[-keep_count:])


def generate_style_summary(style_path, output_path, subject_name, client=None, model_name="gemini-2.0-flash"):
    """
    Generate a comprehensive style summary using Gemini.
    
    Args:
        style_path: Path to the {name}_style.txt file
        output_path: Path to write the output summary
        subject_name: Name of the subject whose style is being analyzed
        client: Optional genai.Client instance
        model_name: Name of the Gemini model to use
    """
    print(f"\n--- Generating Style Summary for {subject_name} ---")
    print(f"  Using model: {model_name}")
    
    # Read the style file
    with open(style_path, 'r', encoding='utf-8') as f:
        style_content = f.read()
    
    print(f"  Loaded style file: {len(style_content):,} characters (~{estimate_tokens(style_content):,} tokens)")
    
    # Parse into sections
    sections = parse_style_sections(style_content)
    print(f"  Found {len(sections)} source file section(s)")
    
    # Initialize Gemini client if not provided
    if not client:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("Error: GEMINI_API_KEY not found")
            return
        client = genai.Client(api_key=api_key)
    
    # Generate the analysis
    print("  Calling Gemini for style analysis...")
    prompt = STYLE_ANALYSIS_PROMPT.format(
        subject_name=subject_name,
        chat_data=style_content
    )
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        analysis = response.text
        print(f"  Analysis generated: {len(analysis):,} characters")
    except Exception as e:
        print(f"  Error calling Gemini: {e}")
        analysis = f"# Style Analysis: {subject_name}\n\n[Error generating analysis: {e}]"
    
    # Calculate example percentage
    example_percentage = calculate_example_percentage(style_content, estimate_tokens(analysis))
    print(f"  Including {example_percentage * 100:.1f}% of original examples")
    
    # Build examples section
    examples_parts = []
    for i, section_content in sections:
        truncated = truncate_section(section_content, example_percentage)
        examples_parts.append(f"## Source File {i + 1} | Subject: {subject_name}\n\n{truncated}")
    
    examples_section = "\n\n---\n\n".join(examples_parts)
    
    # Combine into final output
    final_output = f"""{analysis}

---

# Examples

The following are real conversation examples. The subject is **{subject_name}**.

{examples_section}
"""
    
    # Write to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_output)
    
    final_tokens = estimate_tokens(final_output)
    print(f"  Style summary written to: {output_path}")
    print(f"  Final size: {len(final_output):,} characters (~{final_tokens:,} tokens)")
    
    if final_tokens > TARGET_MAX_TOKENS:
        print(f"  ⚠️  Warning: Exceeded target of {TARGET_MAX_TOKENS:,} tokens (minimum 20% examples enforced)")


if __name__ == "__main__":
    # For testing standalone
    import sys
    if len(sys.argv) >= 3:
        style_path = sys.argv[1]
        subject_name = sys.argv[2]
        output_path = style_path.replace('_style.txt', '_style_summary.txt')
        generate_style_summary(style_path, output_path, subject_name)
    else:
        print("Usage: python style_summarizer.py <style_file_path> <subject_name>")
