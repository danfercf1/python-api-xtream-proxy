#!/usr/bin/env bash
# Generate a new Fernet encryption key for password encryption
set -euo pipefail

echo "Generating new encryption key..."
echo ""

# Check if Python and cryptography are available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed." >&2
    exit 1
fi

# Install cryptography if not present
if ! python3 -c "from cryptography.fernet import Fernet" 2>/dev/null; then
    echo "Installing cryptography library..."
    pip3 install cryptography -q
fi

# Generate key
KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

echo "=============================================="
echo "Generated Encryption Key:"
echo "=============================================="
echo "$KEY"
echo "=============================================="
echo ""
echo "IMPORTANT SECURITY NOTES:"
echo "1. Copy this key to your .env file as ENCRYPTION_KEY"
echo "2. Keep this key SECRET and back it up safely"
echo "3. If you lose this key, encrypted passwords CANNOT be recovered"
echo "4. Store it in a password manager or secure vault"
echo ""
echo "Example .env entry:"
echo "ENCRYPTION_KEY=$KEY"
