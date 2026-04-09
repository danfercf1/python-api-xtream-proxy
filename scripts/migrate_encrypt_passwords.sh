#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Migrate existing plaintext passwords to encrypted format.

Usage:
  scripts/migrate_encrypt_passwords.sh [--env <path>] [--dry-run]

Options:
  --env <path>      Env file to load (default: ./.env if present, else ./.env.example)
  --dry-run         Print what would be done without executing
  --help            Show this help message

Requirements:
  - ENCRYPTION_KEY must be set in the environment
  - Database must be accessible
  - Python with cryptography library must be available

WARNING: Make a database backup before running this script!
EOF
}

ENV_PATH=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_PATH="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$ENV_PATH" ]]; then
  if [[ -f ".env" ]]; then
    ENV_PATH=".env"
  elif [[ -f ".env.example" ]]; then
    ENV_PATH=".env.example"
  else
    echo "No .env or .env.example found. Use --env <path>." >&2
    exit 1
  fi
fi

if [[ ! -f "$ENV_PATH" ]]; then
  echo "Env file not found: $ENV_PATH" >&2
  exit 1
fi

# Load env file
set -a
source "$ENV_PATH"
set +a

# Check encryption key is set
if [[ -z "${ENCRYPTION_KEY:-}" ]]; then
  echo "ERROR: ENCRYPTION_KEY is not set in $ENV_PATH" >&2
  echo "Generate one with: ./scripts/generate_encryption_key.sh" >&2
  exit 1
fi

echo "=========================================="
echo "Password Encryption Migration Tool"
echo "=========================================="
echo ""
echo "Environment: $ENV_PATH"
echo "Database: $MYSQL_DATABASE"
echo "Host: $MYSQL_HOST"
echo ""

if [[ "$DRY_RUN" == "1" ]]; then
  echo "DRY RUN MODE - No changes will be made"
  echo ""
fi

echo "WARNING: This will encrypt all plaintext passwords in the database."
echo "Make sure you have a backup before proceeding!"
echo ""

# Python script to perform the migration
python3 << 'PYTHON_SCRIPT'
import os
import sys
import pymysql
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from crypto_utils import PasswordCipher

# Configuration from environment
DB_HOST = os.getenv("MYSQL_HOST")
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_NAME = os.getenv("MYSQL_DATABASE")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    print("ERROR: Database configuration missing from environment")
    sys.exit(1)

try:
    cipher = PasswordCipher()
except Exception as e:
    print(f"ERROR: Failed to initialize cipher: {e}")
    sys.exit(1)

try:
    connection = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with connection.cursor() as cursor:
        # Get all users
        cursor.execute("SELECT id, username, password FROM users")
        users = cursor.fetchall()
        
        print(f"Found {len(users)} users in database")
        print("")
        
        encrypted_count = 0
        skipped_count = 0
        error_count = 0
        
        for user in users:
            user_id = user['id']
            username = user['username']
            password = user['password']
            
            # Check if already encrypted
            if cipher.is_encrypted(password):
                print(f"[{user_id}] {username}: Already encrypted, skipping")
                skipped_count += 1
                continue
            
            # Encrypt the password
            try:
                encrypted_password = cipher.encrypt(password)
                
                if DRY_RUN:
                    print(f"[{user_id}] {username}: Would encrypt (dry run)")
                else:
                    cursor.execute(
                        "UPDATE users SET password = %s WHERE id = %s",
                        (encrypted_password, user_id)
                    )
                    print(f"[{user_id}] {username}: Encrypted successfully")
                
                encrypted_count += 1
            except Exception as e:
                print(f"[{user_id}] {username}: ERROR - {e}")
                error_count += 1
        
        if not DRY_RUN and encrypted_count > 0:
            connection.commit()
        
        print("")
        print("==========================================")
        print("Migration Summary")
        print("==========================================")
        print(f"Total users: {len(users)}")
        print(f"Encrypted: {encrypted_count}")
        print(f"Already encrypted (skipped): {skipped_count}")
        print(f"Errors: {error_count}")
        
        if DRY_RUN:
            print("")
            print("This was a DRY RUN. No changes were made.")
            print("Run without --dry-run to apply changes.")
        
except pymysql.Error as e:
    print(f"Database error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)
finally:
    if 'connection' in locals():
        connection.close()
PYTHON_SCRIPT
DRY_RUN="$DRY_RUN"

if [[ "$DRY_RUN" == "1" ]]; then
  echo ""
  echo "To apply changes, run without --dry-run"
fi
