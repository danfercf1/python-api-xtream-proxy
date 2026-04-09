"""
Cryptographic utilities for sensitive data protection.
Provides encryption/decryption for passwords at rest.
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PasswordCipher:
    """Encrypts/decrypts passwords using Fernet symmetric encryption.
    
    Usage:
        cipher = PasswordCipher()  # Uses ENCRYPTION_KEY from env
        encrypted = cipher.encrypt("my_password")
        decrypted = cipher.decrypt(encrypted)
    """
    
    def __init__(self, key: str | None = None):
        """Initialize cipher with encryption key.
        
        Args:
            key: Base64-encoded 32-byte key. If None, reads from ENCRYPTION_KEY env var.
        """
        if key is None:
            key = os.environ.get('ENCRYPTION_KEY')
        
        if not key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable is required. "
                "Generate one with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.
        
        Args:
            plaintext: The string to encrypt
            
        Returns:
            Base64-encoded encrypted string with 'enc:' prefix
        """
        if not plaintext:
            return plaintext
        
        # Check if already encrypted (to avoid double encryption)
        if plaintext.startswith('enc:'):
            return plaintext
        
        encrypted = self._fernet.encrypt(plaintext.encode('utf-8'))
        return 'enc:' + encrypted.decode('utf-8')
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string.
        
        Args:
            ciphertext: The encrypted string (with 'enc:' prefix)
            
        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ciphertext
        
        # Check if it's plaintext (legacy)
        if not ciphertext.startswith('enc:'):
            return ciphertext
        
        encrypted_data = ciphertext[4:].encode('utf-8')
        decrypted = self._fernet.decrypt(encrypted_data)
        return decrypted.decode('utf-8')
    
    def is_encrypted(self, value: str) -> bool:
        """Check if a value is already encrypted.
        
        Args:
            value: The value to check
            
        Returns:
            True if encrypted, False otherwise
        """
        return bool(value and value.startswith('enc:'))


def generate_encryption_key() -> str:
    """Generate a new encryption key.
    
    Returns:
        A URL-safe base64-encoded 32-byte key
    """
    return Fernet.generate_key().decode()


# Backward compatibility: allow importing from database.py
def get_cipher():
    """Get singleton cipher instance."""
    if not hasattr(get_cipher, '_instance'):
        get_cipher._instance = PasswordCipher()
    return get_cipher._instance
