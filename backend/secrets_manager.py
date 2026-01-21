"""
NullTale Secrets Manager
------------------------
Securely stores API keys and other secrets in an encrypted local file.
Keys are encrypted using Fernet (AES-128-CBC) with a machine-derived key.
"""
import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet

# Secrets file location (outside of git-tracked folders)
SECRETS_DIR = Path(__file__).parent / "data" / ".secrets"
SECRETS_FILE = SECRETS_DIR / "api_keys.enc"


def _get_machine_key() -> bytes:
    """
    Generate a machine-specific encryption key.
    Uses a combination of factors to create a unique key per machine.
    """
    # Combine machine-specific identifiers
    identifiers = []
    
    # Username
    identifiers.append(os.environ.get("USERNAME", os.environ.get("USER", "default")))
    
    # Computer name
    identifiers.append(os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")))
    
    # This file's path (unique per installation)
    identifiers.append(str(Path(__file__).resolve()))
    
    # Combine and hash
    combined = ":".join(identifiers)
    hash_bytes = hashlib.sha256(combined.encode()).digest()
    
    # Fernet requires a 32-byte base64-encoded key
    return base64.urlsafe_b64encode(hash_bytes)


def _get_cipher():
    """Get the Fernet cipher instance."""
    return Fernet(_get_machine_key())


def save_secret(key: str, value: str) -> bool:
    """
    Save a secret securely.
    
    Args:
        key: Secret identifier (e.g., "wavespeed_api_key")
        value: The secret value to store
    
    Returns:
        True if saved successfully
    """
    try:
        # Ensure secrets directory exists
        SECRETS_DIR.mkdir(exist_ok=True)
        
        # Add to .gitignore if not already there
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        gitignore_entry = "backend/data/.secrets/"
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            if gitignore_entry not in content:
                with open(gitignore_path, "a") as f:
                    f.write(f"\n# Encrypted secrets\n{gitignore_entry}\n")
        
        # Load existing secrets
        secrets = _load_all_secrets()
        
        # Add/update the secret
        secrets[key] = value
        
        # Encrypt and save
        cipher = _get_cipher()
        encrypted = cipher.encrypt(json.dumps(secrets).encode())
        
        SECRETS_FILE.write_bytes(encrypted)
        return True
        
    except Exception as e:
        print(f"Error saving secret: {e}")
        return False


def get_secret(key: str, fallback_env: Optional[str] = None) -> Optional[str]:
    """
    Retrieve a secret.
    
    Args:
        key: Secret identifier
        fallback_env: Environment variable to check if secret not found
    
    Returns:
        The secret value, or None if not found
    """
    secrets = _load_all_secrets()
    value = secrets.get(key)
    
    # Fallback to environment variable
    if not value and fallback_env:
        value = os.environ.get(fallback_env)
    
    return value


def delete_secret(key: str) -> bool:
    """Delete a secret."""
    try:
        secrets = _load_all_secrets()
        if key in secrets:
            del secrets[key]
            
            if secrets:
                cipher = _get_cipher()
                encrypted = cipher.encrypt(json.dumps(secrets).encode())
                SECRETS_FILE.write_bytes(encrypted)
            else:
                # Remove file if no secrets left
                if SECRETS_FILE.exists():
                    SECRETS_FILE.unlink()
            
            return True
        return False
    except Exception:
        return False


def has_secret(key: str) -> bool:
    """Check if a secret exists."""
    secrets = _load_all_secrets()
    return key in secrets


def _load_all_secrets() -> dict:
    """Load all secrets from encrypted file."""
    if not SECRETS_FILE.exists():
        return {}
    
    try:
        cipher = _get_cipher()
        encrypted = SECRETS_FILE.read_bytes()
        decrypted = cipher.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except Exception:
        # If decryption fails (wrong machine, corrupted file), return empty
        return {}


# Convenience functions for specific keys
def get_wavespeed_key() -> Optional[str]:
    """Get WaveSpeed API key."""
    return get_secret("wavespeed_api_key", fallback_env="WAVESPEED_API_KEY")


def save_wavespeed_key(api_key: str) -> bool:
    """Save WaveSpeed API key."""
    return save_secret("wavespeed_api_key", api_key)


def has_wavespeed_key() -> bool:
    """Check if WaveSpeed API key is configured."""
    return bool(get_wavespeed_key())
