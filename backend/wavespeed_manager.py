"""
WaveSpeed Voice Manager
-----------------------
Simple interface for WaveSpeed MiniMax Speech 2.6 Turbo API.
Users only need to provide:
1. API key
2. Audio file for voice cloning

All other settings are handled automatically with sensible defaults.
"""
import os
import io
import requests
import logging
from pathlib import Path
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("WaveSpeedManager")


class WaveSpeedManager:
    """
    Simplified WaveSpeed TTS with voice cloning.
    
    Usage:
        manager = WaveSpeedManager(api_key="your-key")
        
        # Clone your voice (one-time setup)
        manager.clone_voice("my_voice", "path/to/audio.wav")
        
        # Speak with cloned voice
        audio_bytes = manager.speak("Hello!", "my_voice")
    """
    
    # API Configuration
    BASE_URL = "https://api.wavespeed.ai"
    CLONE_ENDPOINT = "/api/v3/minimax/voice-clone"
    TTS_ENDPOINT = "/api/v3/minimax/speech-2.6-turbo"
    TTS_STREAM_ENDPOINT = "/api/v3/minimax/speech-2.6-turbo/stream"
    
    # System voices (no cloning needed)
    SYSTEM_VOICES = [
        "Wise_Woman",
        "Friendly_Person", 
        "Deep_Voice_Man",
        "Calm_Woman",
        "Inspirational_girl"
    ]
    
    # Default TTS settings (optimized for natural speech)
    DEFAULT_SETTINGS = {
        "speed": 1.0,
        "volume": 1.0,
        "pitch": 0,
        "sample_rate": 32000,
        "format": "wav",
        "english_normalization": True
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize WaveSpeed manager.
        
        Args:
            api_key: WaveSpeed API key. If not provided, reads from 
                     WAVESPEED_API_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("WAVESPEED_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Pass api_key or set WAVESPEED_API_KEY environment variable.\n"
                "Get your API key from: https://wavespeed.ai"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Store cloned voice IDs
        self._cloned_voices = {}
        
        logger.info("WaveSpeedManager initialized")
    
    def clone_voice(
        self, 
        voice_name: str, 
        audio_path: str,
        noise_reduction: bool = True,
        volume_normalization: bool = True
    ) -> str:
        """
        Clone a voice from an audio file.
        
        Args:
            voice_name: Name for this voice (will be used as ID).
                        Must be 8+ chars, start with letter, alphanumeric.
            audio_path: Path to audio file (MP3, M4A, or WAV, 10s-5min, max 20MB)
            noise_reduction: Auto-clean background noise (recommended)
            volume_normalization: Auto-level volume (recommended)
        
        Returns:
            The voice_id to use in speak() calls
        
        Example:
            manager.clone_voice("MyVoice01", "recording.wav")
        """
        import base64
        
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Validate voice name format (min 8 chars, starts with letter, alphanumeric)
        voice_id = self._format_voice_id(voice_name)
        
        logger.info(f"Cloning voice '{voice_id}' from {audio_file.name}...")
        
        # Step 1: Upload audio file to WaveSpeed Media Upload API
        mime_type = self._get_mime_type(audio_file)
        with open(audio_file, "rb") as f:
            files = {"file": (audio_file.name, f, mime_type)}
            upload_response = requests.post(
                f"{self.BASE_URL}/api/v3/media/upload/binary",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files
            )
        
        if upload_response.status_code != 200:
            raise Exception(f"Audio upload failed: {upload_response.status_code} - {upload_response.text}")
        
        upload_result = upload_response.json()
        
        # DEBUG: Log upload response
        logger.info(f"Upload response: {upload_result}")
        
        # Handle different response structures
        data_obj = upload_result.get("data") if isinstance(upload_result.get("data"), dict) else {}
        audio_url = (
            data_obj.get("download_url") or 
            upload_result.get("download_url") or 
            upload_result.get("url")
        )
        
        # If data is a string, it might be the URL directly
        if not audio_url and isinstance(upload_result.get("data"), str):
            audio_url = upload_result.get("data")
        
        if not audio_url:
            raise Exception(f"No download_url in upload response: {upload_result}")
        
        logger.info(f"Audio uploaded successfully: {audio_url}")
        
        # Step 2: Call voice clone endpoint with the uploaded audio URL
        payload = {
            "model": "speech-2.6-turbo",
            "audio": audio_url,
            "custom_voice_id": voice_id,
            "text": "Hello, this is a test of my cloned voice."
        }
        
        response = requests.post(
            f"{self.BASE_URL}{self.CLONE_ENDPOINT}",
            headers=self.headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"Voice cloning failed: {response.status_code} - {response.text}")
        
        result = response.json()
        

        
        # Extract the actual voice_id from WaveSpeed's response
        # The API may assign a different ID than what we requested
        data_obj = result.get("data") if isinstance(result.get("data"), dict) else {}
        
        # Check if async (has polling URL)
        result_url = data_obj.get("urls", {}).get("get")
        if result_url:
            logger.info("Voice cloning initiated (async). Polling for completion...")
            import time
            max_attempts = 120  # Wait up to 120 seconds
            
            for attempt in range(max_attempts):
                time.sleep(1)
                poll_response = requests.get(result_url, headers=self.headers)
                
                if poll_response.status_code == 200:
                    poll_result = poll_response.json()
                    poll_data = poll_result.get("data") if isinstance(poll_result.get("data"), dict) else {}
                    status = poll_data.get("status") or poll_result.get("status")
                    
                    if status == "completed":
                        # Success!
 

                        # Extract voice ID from response
                        outputs = poll_data.get("outputs", [])
                        output_voice_id = None
                        if outputs and len(outputs) > 0:
                            first_output = outputs[0]
                            if isinstance(first_output, dict):
                                output_voice_id = first_output.get("voice_id")
                        
                        returned_voice_id = (
                            poll_data.get("voice_id") or 
                            poll_data.get("custom_voice_id") or
                            output_voice_id or
                            voice_id  # Fallback
                        )
                        break
                    elif status == "failed":

                        
                        error = poll_data.get("error") or poll_result.get("error", "Unknown error")
                        raise Exception(f"Voice cloning failed: {error}")
            else:
                raise Exception("Voice cloning timeout: process did not complete in 120 seconds")
        else:
            # Sync response (fallback parsing)
            returned_voice_id = (
                result.get("voice_id") or 
                data_obj.get("voice_id") or 
                data_obj.get("custom_voice_id") or
                voice_id  # Fallback to our requested ID
            )
        
        # Store the voice ID
        self._cloned_voices[voice_name] = returned_voice_id
        
        logger.info(f"Voice '{returned_voice_id}' cloned successfully! (Response: {result})")
        return returned_voice_id
    
    def speak(
        self, 
        text: str, 
        voice: str = "Deep_Voice_Man",
        **kwargs
    ) -> io.BytesIO:
        """
        Generate speech from text.
        
        Args:
            text: Text to speak (max 10,000 characters)
            voice: Voice name (system voice or cloned voice name)
            **kwargs: Optional overrides (speed, volume, pitch, emotion, etc.)
        
        Returns:
            BytesIO containing WAV audio data
        
        Example:
            audio = manager.speak("Hello world!", "MyVoice01")
            with open("output.wav", "wb") as f:
                f.write(audio.read())
        """
        if not text:
            raise ValueError("Text cannot be empty")
        
        if len(text) > 10000:
            raise ValueError("Text exceeds 10,000 character limit")
        
        # Resolve voice ID (check if it's a cloned voice name)
        voice_id = self._cloned_voices.get(voice, voice)
        
        # Build request with defaults + overrides
        payload = {
            "model": "speech-2.6-turbo",
            "text": text,
            "voice_id": voice_id,
            **self.DEFAULT_SETTINGS,
            **kwargs
        }
        
        logger.info(f"Generating speech with voice '{voice_id}'...")
        
        response = requests.post(
            f"{self.BASE_URL}{self.TTS_ENDPOINT}",
            headers=self.headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"TTS failed: {response.status_code} - {response.text}")
        
        # Handle response - could be direct audio or async JSON with result URL
        content_type = response.headers.get("Content-Type", "")
        
        if "audio" in content_type:
            # Direct audio response
            buffer = io.BytesIO(response.content)
            buffer.seek(0)
            return buffer
        else:
            # Async JSON response - need to poll for result
            import time
            result = response.json()
            
            # Check for direct audio URL first
            audio_url = result.get("audio_url") or result.get("data", {}).get("audio_url")
            
            if audio_url:
                audio_response = requests.get(audio_url)
                buffer = io.BytesIO(audio_response.content)
                buffer.seek(0)
                return buffer
            
            # Otherwise poll the result URL (async pattern)
            data_obj = result.get("data") if isinstance(result.get("data"), dict) else {}
            result_url = data_obj.get("urls", {}).get("get")
            
            if result_url:
                # Poll for result with timeout
                max_attempts = 30
                for attempt in range(max_attempts):
                    time.sleep(1)  # Wait 1 second between polls
                    poll_response = requests.get(result_url, headers=self.headers)
                    if poll_response.status_code == 200:
                        poll_result = poll_response.json()
                        poll_data = poll_result.get("data") if isinstance(poll_result.get("data"), dict) else {}
                        
                        status = poll_data.get("status") or poll_result.get("status")
                        
                        if status == "completed":
                            # Get audio URL from outputs
                            outputs = poll_data.get("outputs") or poll_result.get("outputs", [])
                            if outputs and len(outputs) > 0:
                                # Handle both string URLs and dict objects
                                first_output = outputs[0]
                                if isinstance(first_output, str):
                                    audio_url = first_output
                                elif isinstance(first_output, dict):
                                    audio_url = first_output.get("audio") or first_output.get("url") or first_output.get("audio_url")
                                else:
                                    audio_url = None
                                
                                if audio_url and isinstance(audio_url, str) and audio_url.startswith("http"):
                                    audio_response = requests.get(audio_url)
                                    buffer = io.BytesIO(audio_response.content)
                                    buffer.seek(0)
                                    return buffer
                            raise Exception(f"No audio in completed response: {poll_result}")
                        elif status == "failed":
                            error = poll_data.get("error") or poll_result.get("error", "Unknown error")
                            raise Exception(f"TTS job failed: {error}")
                        # else: still processing, continue polling
                
                raise Exception("TTS timeout: job did not complete in 30 seconds")
            
            raise Exception(f"No audio in response: {result}")
    
    def speak_stream(
        self, 
        text: str, 
        voice: str = None,
        **kwargs
    ):
        """
        Generate speech from text with real-time streaming.
        Uses WaveSpeed's /stream endpoint for true chunked audio delivery.
        
        Args:
            text: Text to speak (max 10,000 characters)
            voice: Voice name (cloned voice ID)
            **kwargs: Optional overrides (speed, volume, pitch, etc.)
        
        Yields:
            bytes: WAV audio chunks for browser playback
        """
        import struct
        import base64
        import json as json_lib
        
        if not text:
            raise ValueError("Text cannot be empty")
        
        if len(text) > 10000:
            raise ValueError("Text exceeds 10,000 character limit")
        
        # Resolve voice ID
        voice_id = self._cloned_voices.get(voice, voice)
        
        # WaveSpeed returns audio at 32000 Hz
        sample_rate = 32000
        
        # Build request for streaming endpoint
        payload = {
            "model": "speech-2.6-turbo",
            "text": text,
            "voice_id": voice_id,
            "sample_rate": sample_rate,
            "format": "pcm",
            "speed": kwargs.get("speed", 1.0),
            "volume": kwargs.get("volume", 1.0),
            "pitch": kwargs.get("pitch", 0),
            "english_normalization": True
        }
        
        logger.info(f"Starting TRUE streaming TTS with voice '{voice_id}'...")
        
        # Use streaming endpoint with SSE
        response = requests.post(
            f"{self.BASE_URL}{self.TTS_STREAM_ENDPOINT}",
            headers=self.headers,
            json=payload,
            stream=True
        )
        
        # DEBUG logging
        print(f"[DEBUG] Stream response status: {response.status_code}")
        print(f"[DEBUG] Stream response content-type: {response.headers.get('Content-Type')}")
        
        if response.status_code != 200:
            # Fall back to polling method if streaming endpoint doesn't exist
            print(f"[DEBUG] Stream endpoint failed, falling back to polling...")
            logger.warning(f"Stream endpoint failed ({response.status_code}), falling back to polling...")
            for chunk in self._speak_polling(text, voice_id, sample_rate, **kwargs):
                yield chunk
            return
        
        content_type = response.headers.get("Content-Type", "")
        
        # Create WAV header function
        def make_wav_header(data_size, sr=32000, channels=1, bits=16):
            byte_rate = sr * channels * bits // 8
            block_align = channels * bits // 8
            return struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16, 1,
                channels, sr, byte_rate, block_align, bits,
                b'data', data_size
            )
        
        if "text/event-stream" in content_type:
            # True SSE streaming - parse event stream
            print(f"[DEBUG] Entering SSE streaming path")
            pcm_buffer = b''
            # NOTE: Increased buffer to ~0.5s (32000 bytes) to prevent frontend playback gaps/glitches
            chunk_size_target = 32000  # ~500ms of audio at 32kHz 16-bit mono
            chunk_count = 0
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data:'):
                        data = line_str[5:].strip()
                        if data and data != '[DONE]':
                            try:
                                event_data = json_lib.loads(data)
                                inner_data = event_data.get('data', {})
                                
                                # Check completion
                                status = inner_data.get('status')
                                # Status 1 = Processing/Streaming
                                # Status 2 = Completed
                                is_done = (status == 2)
                                
                                # Extract audio chunk
                                # NOTE: WaveSpeed returns HEX string, not base64!
                                # Only process audio from status 1 (streaming/incremental).
                                # Status 2 (completed) contains the FULL audio, which causes duplication if processed.
                                if status == 1:
                                    audio_hex = inner_data.get('audio')
                                else:
                                    audio_hex = None
                                
                                if audio_hex and isinstance(audio_hex, str):
                                    # Convert hex string to bytes
                                    try:
                                        audio_bytes = bytes.fromhex(audio_hex)
                                        pcm_buffer += audio_bytes
                                        
                                        # Yield chunks when we have enough data
                                        while len(pcm_buffer) >= chunk_size_target:
                                            chunk = pcm_buffer[:chunk_size_target]
                                            pcm_buffer = pcm_buffer[chunk_size_target:]
                                            wav_header = make_wav_header(len(chunk), sample_rate)
                                            yield wav_header + chunk
                                    except ValueError:
                                        pass
                                
                                if is_done:
                                    break
                            except Exception:
                                pass
            
            # Yield remaining data
            if pcm_buffer:
                wav_header = make_wav_header(len(pcm_buffer), sample_rate)
                yield wav_header + pcm_buffer
        else:
            # Response is not SSE, might be direct audio or JSON
            # Fall back to polling
            print(f"[DEBUG] Not SSE, falling back to polling. Content-type: {content_type}")
            for chunk in self._speak_polling(text, voice_id, sample_rate, **kwargs):
                yield chunk
    
    def _speak_polling(self, text, voice_id, sample_rate, **kwargs):
        """Fallback polling-based TTS."""
        import struct
        import time
        
        payload = {
            "model": "speech-2.6-turbo",
            "text": text,
            "voice_id": voice_id,
            "sample_rate": sample_rate,
            "format": "pcm",
            "speed": kwargs.get("speed", 1.0),
            "volume": kwargs.get("volume", 1.0),
            "pitch": kwargs.get("pitch", 0),
            "english_normalization": True
        }
        
        response = requests.post(
            f"{self.BASE_URL}{self.TTS_ENDPOINT}",
            headers=self.headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"TTS failed: {response.status_code} - {response.text}")
        
        result = response.json()
        data_obj = result.get("data") if isinstance(result.get("data"), dict) else {}
        result_url = data_obj.get("urls", {}).get("get")
        
        if result_url:
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(1)
                poll_response = requests.get(result_url, headers=self.headers)
                if poll_response.status_code == 200:
                    poll_result = poll_response.json()
                    poll_data = poll_result.get("data") if isinstance(poll_result.get("data"), dict) else {}
                    status = poll_data.get("status") or poll_result.get("status")
                    
                    if status == "completed":
                        outputs = poll_data.get("outputs") or poll_result.get("outputs", [])
                        if outputs and len(outputs) > 0:
                            first_output = outputs[0]
                            if isinstance(first_output, str):
                                audio_url = first_output
                            elif isinstance(first_output, dict):
                                audio_url = first_output.get("audio") or first_output.get("url")
                            else:
                                audio_url = None
                            
                            if audio_url:
                                audio_response = requests.get(audio_url)
                                audio_data = audio_response.content
                                
                                def make_wav_header(data_size, sr=32000, channels=1, bits=16):
                                    byte_rate = sr * channels * bits // 8
                                    block_align = channels * bits // 8
                                    return struct.pack(
                                        '<4sI4s4sIHHIIHH4sI',
                                        b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16, 1,
                                        channels, sr, byte_rate, block_align, bits,
                                        b'data', data_size
                                    )
                                
                                wav_header = make_wav_header(len(audio_data), sample_rate)
                                yield wav_header + audio_data
                                return
                    elif status == "failed":
                        error = poll_data.get("error") or poll_result.get("error", "Unknown")
                        raise Exception(f"TTS failed: {error}")
            
            raise Exception("TTS timeout")

    
    def list_voices(self) -> dict:
        """
        List available voices.
        
        Returns:
            Dict with 'system' and 'cloned' voice lists
        """
        return {
            "system": self.SYSTEM_VOICES.copy(),
            "cloned": list(self._cloned_voices.keys())
        }
    
    def _format_voice_id(self, name: str) -> str:
        """Format voice name to valid voice_id (8+ chars, starts with letter, alphanumeric)."""
        import time
        
        # Remove invalid characters
        clean = ''.join(c for c in name if c.isalnum() or c == '_')
        
        # Ensure starts with letter
        if not clean or not clean[0].isalpha():
            clean = "Voice" + clean
        
        # Add timestamp suffix for uniqueness
        timestamp = str(int(time.time()))[-6:]  # Last 6 digits of timestamp
        clean = clean + timestamp
        
        # Ensure minimum 8 characters
        if len(clean) < 8:
            clean = clean + "0" * (8 - len(clean))
        
        return clean
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Get MIME type for audio file."""
        suffix = file_path.suffix.lower()
        mime_types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4"
        }
        return mime_types.get(suffix, "audio/wav")


# Convenience function for quick usage
def quick_speak(text: str, api_key: str, voice: str = "Deep_Voice_Man") -> io.BytesIO:
    """
    Quick one-liner TTS without creating a manager instance.
    
    Example:
        audio = quick_speak("Hello!", api_key="your-key")
    """
    manager = WaveSpeedManager(api_key=api_key)
    return manager.speak(text, voice)
