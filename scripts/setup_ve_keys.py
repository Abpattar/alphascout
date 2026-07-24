#!/usr/bin/env python3
"""
Quick credential setup using VE.txt keys
"""
import os
import json
from pathlib import Path
from cryptography.fernet import Fernet

# Read keys from VE.txt
ve_path = Path("/home/neo/Codes/VE.txt")
if not ve_path.exists():
    print("VE.txt not found!")
    exit(1)

with open(ve_path) as f:
    content = f.read()

# Parse keys
creds = {}
for line in content.split("\n"):
    if "tradekey" in line.lower() and ":" in line:
        parts = line.split(":")
        if "tradekey 0" in line.lower() or "GROQ_API_KEY=" in line:
            key = parts[-1].strip().strip('"')
            if key.startswith("gsk_"):
                creds["GROQ_API_KEY"] = key
        elif "tradekey 2" in line.lower():
            key = parts[-1].strip().strip('"')
            if key.startswith("gsk_"):
                creds["GROQ_API_KEY_2"] = key
        elif "tradekey 3" in line.lower():
            key = parts[-1].strip().strip('"')
            if key.startswith("gsk_"):
                creds["GROQ_API_KEY_3"] = key
        elif "tradekey 4" in line.lower():
            key = parts[-1].strip().strip('"')
            if key.startswith("gsk_"):
                creds["GROQ_API_KEY_4"] = key
        elif "tradekey 5" in line.lower():
            key = parts[-1].strip().strip('"')
            if key.startswith("gsk_"):
                creds["GROQ_API_KEY_5"] = key
    elif "OpenRouter" in line and ":" in line:
        key = line.split(":")[-1].strip()
        if key.startswith("sk-or-"):
            creds["OPENROUTER_API_KEY"] = key
    elif "Cerebras" in line and ":" in line:
        key = line.split(":")[-1].strip()
        if key.startswith("csk-"):
            creds["CEREBRAS_API_KEY"] = key
    elif "Gemini" in line and ":" in line:
        key = line.split(":")[-1].strip()
        if key.startswith("AQ."):
            creds["GEMINI_API_KEY"] = key

print("Found credentials:")
for k, v in creds.items():
    print(f"  {k}: {v[:20]}..." if len(v) > 20 else f"  {k}: {v}")

# Encrypt and save
CRED_DIR = Path("/home/neo/Codes/alphascout/data/.credentials")
CRED_DIR.mkdir(parents=True, exist_ok=True)
CRED_FILE = CRED_DIR / "credentials.enc"
KEY_FILE = CRED_DIR / "key.bin"

if not KEY_FILE.exists():
    KEY_FILE.write_bytes(Fernet.generate_key())
    KEY_FILE.chmod(0o600)

key = KEY_FILE.read_bytes()
f = Fernet(key)

data = "\n".join(f"{k}={v}" for k, v in creds.items() if v)
CRED_FILE.write_bytes(f.encrypt(data.encode()))
CRED_FILE.chmod(0o600)

print(f"\n✅ Saved encrypted to {CRED_FILE}")

# Also export to .env for easy loading
env_file = Path("/home/neo/Codes/alphascout/.env")
lines = [f'{k}="{v}"' for k, v in creds.items() if v]
env_file.write_text("\n".join(lines))
print(f"✅ Saved to {env_file}")

print("\n📝 Note: Add Zerodha & Telegram credentials manually if needed:")
print("  export KITE_API_KEY=...")
print("  export KITE_API_SECRET=...")
print("  export KITE_ACCESS_TOKEN=...")
print("  export TELEGRAM_BOT_TOKEN=...")
print("  export TELEGRAM_CHAT_ID=...")