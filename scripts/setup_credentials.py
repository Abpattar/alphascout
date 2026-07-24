#!/usr/bin/env python3
"""
AlphaScout Credential Setup Wizard
Run once to configure all API keys and tokens
"""

import os
import sys
import getpass
from pathlib import Path
from cryptography.fernet import Fernet

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CRED_DIR = ROOT / "data" / ".credentials"
CRED_DIR.mkdir(parents=True, exist_ok=True)
CRED_FILE = CRED_DIR / "credentials.enc"
KEY_FILE = CRED_DIR / "key.bin"


def get_or_create_key() -> bytes:
    """Get or create encryption key"""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    return key


def encrypt_data(data: str, key: bytes) -> bytes:
    return Fernet(key).encrypt(data.encode())


def decrypt_data(data: bytes, key: bytes) -> str:
    return Fernet(key).decrypt(data).decode()


def load_credentials() -> dict:
    """Load encrypted credentials"""
    if not CRED_FILE.exists():
        return {}
    key = get_or_create_key()
    try:
        data = decrypt_data(CRED_FILE.read_bytes(), key)
        creds = {}
        for line in data.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k] = v
        return creds
    except Exception:
        return {}


def save_credentials(creds: dict):
    """Save encrypted credentials"""
    key = get_or_create_key()
    data = "\n".join(f"{k}={v}" for k, v in creds.items() if v)
    CRED_FILE.write_bytes(encrypt_data(data, key))
    CRED_FILE.chmod(0o600)
    print(f"✅ Credentials saved to {CRED_FILE}")


def get_input(prompt: str, secret: bool = False, default: str = "") -> str:
    """Get user input with optional secret masking"""
    if default:
        prompt += f" [{default[:8]}...]" if secret else f" [{default}]"
    prompt += ": "

    while True:
        if secret:
            val = getpass.getpass(prompt)
        else:
            val = input(prompt).strip()

        if val:
            return val
        if default:
            return default
        print("   ⚠️  Required field. Please enter a value.")


def print_banner():
    print("""
╔════════════════════════════════════════════════════════════════════════╗
║                    ALPHASCOUT - CREDENTIAL SETUP                       ║
║          Multi-Sector Small-Cap News → Trade Signal Bot               ║
╚════════════════════════════════════════════════════════════════════════╝
""")


def setup_llm_keys(creds: dict) -> dict:
    print("\n┌────────────────────────────────────────────────────────────────────┐")
    print("│  LLM PROVIDERS (All Free Tier - Required)                          │")
    print("└────────────────────────────────────────────────────────────────────┘")

    print("\n1. GROQ (Primary - Llama-3.3-70B)")
    print("   Get keys: https://console.groq.com/keys")
    print("   Create MULTIPLE keys for rotation (rate limit: 30 RPM each)")
    creds["GROQ_API_KEY"] = get_input("   GROQ_API_KEY_1", secret=True, default=creds.get("GROQ_API_KEY", ""))
    creds["GROQ_API_KEY_2"] = get_input("   GROQ_API_KEY_2", secret=True, default=creds.get("GROQ_API_KEY_2", ""))
    creds["GROQ_API_KEY_3"] = get_input("   GROQ_API_KEY_3", secret=True, default=creds.get("GROQ_API_KEY_3", ""))
    creds["GROQ_API_KEY_4"] = get_input("   GROQ_API_KEY_4", secret=True, default=creds.get("GROQ_API_KEY_4", ""))
    creds["GROQ_API_KEY_5"] = get_input("   GROQ_API_KEY_5", secret=True, default=creds.get("GROQ_API_KEY_5", ""))

    print("\n2. OPENROUTER (Unlimited free models)")
    print("   Get key: https://openrouter.ai/keys")
    creds["OPENROUTER_API_KEY"] = get_input("   OPENROUTER_API_KEY", secret=True, default=creds.get("OPENROUTER_API_KEY", ""))

    print("\n3. CEREBRAS (Fast inference, generous free tier)")
    print("   Get key: https://cerebras.ai/")
    creds["CEREBRAS_API_KEY"] = get_input("   CEREBRAS_API_KEY", secret=True, default=creds.get("CEREBRAS_API_KEY", ""))

    print("\n4. GEMINI (Google AI Studio - 1.5 Flash free)")
    print("   Get key: https://aistudio.google.com/app/apikey")
    creds["GEMINI_API_KEY"] = get_input("   GEMINI_API_KEY", secret=True, default=creds.get("GEMINI_API_KEY", ""))

    return creds


def setup_zerodha(creds: dict) -> dict:
    print("\n┌────────────────────────────────────────────────────────────────────┐")
    print("│  ZERODHA KITE CONNECT (Auto-Execute @ 90%+ Confidence)             │")
    print("└────────────────────────────────────────────────────────────────────┘")
    print("\n   1. Go to: https://developers.kite.trade/apps/new")
    print("   2. Create app: Name='AlphaScout', Redirect URL='http://127.0.0.1:5000/callback'")
    print("   3. Copy API Key and API Secret")
    print("   4. We'll generate Access Token next\n")

    creds["KITE_API_KEY"] = get_input("   KITE_API_KEY", secret=True, default=creds.get("KITE_API_KEY", ""))
    creds["KITE_API_SECRET"] = get_input("   KITE_API_SECRET", secret=True, default=creds.get("KITE_API_SECRET", ""))

    if creds["KITE_API_KEY"] and creds["KITE_API_SECRET"]:
        print("\n   📋 Generate Access Token:")
        print(f"   Open this URL in browser:")
        print(f"   https://kite.trade/connect/login?v=3&api_key={creds['KITE_API_KEY']}")
        print("   Login → Authorize → Redirects to http://127.0.0.1:5000/callback?request_token=XXX")
        print("   Copy the 'request_token' from the URL")
        request_token = get_input("   REQUEST_TOKEN (from redirect URL)", secret=True)

        if request_token:
            try:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=creds["KITE_API_KEY"])
                data = kite.generate_session(request_token, api_secret=creds["KITE_API_SECRET"])
                creds["KITE_ACCESS_TOKEN"] = data["access_token"]
                print("   ✅ Access token generated successfully!")
            except Exception as e:
                print(f"   ❌ Failed: {e}")
                print("   You can run setup again later to generate token")

    return creds


def setup_telegram(creds: dict) -> dict:
    print("\n┌────────────────────────────────────────────────────────────────────┐")
    print("│  TELEGRAM BOT (For Alert Notifications)                             │")
    print("└────────────────────────────────────────────────────────────────────┘")
    print("\n   1. Message @BotFather on Telegram")
    print("   2. Send: /newbot")
    print("   3. Name: AlphaScout Alerts")
    print("   4. Username: alphascout_alerts_bot (must end with _bot)")
    print("   5. Copy the BOT_TOKEN\n")

    creds["TELEGRAM_BOT_TOKEN"] = get_input("   TELEGRAM_BOT_TOKEN", secret=True, default=creds.get("TELEGRAM_BOT_TOKEN", ""))

    if creds["TELEGRAM_BOT_TOKEN"]:
        print("\n   6. Message your bot anything, then visit:")
        print(f"   https://api.telegram.org/bot{creds['TELEGRAM_BOT_TOKEN']}/getUpdates")
        print("   Find 'chat':{'id': YOUR_CHAT_ID}")
        creds["TELEGRAM_CHAT_ID"] = get_input("   TELEGRAM_CHAT_ID", default=creds.get("TELEGRAM_CHAT_ID", ""))

    return creds


def setup_capital(creds: dict) -> dict:
    print("\n┌────────────────────────────────────────────────────────────────────┐")
    print("│  TRADING CAPITAL (For 3% Risk Position Sizing)                     │")
    print("└────────────────────────────────────────────────────────────────────┘")
    print("\n   Enter total capital for position sizing (e.g., 100000 for ₹1L)")
    creds["TRADING_CAPITAL"] = get_input("   TRADING_CAPITAL (₹)", default=creds.get("TRADING_CAPITAL", "100000"))
    return creds


def export_to_env(creds: dict):
    print("\n┌────────────────────────────────────────────────────────────────────┐")
    print("│  EXPORT TO SHELL (Optional - for other tools)                      │")
    print("└────────────────────────────────────────────────────────────────────┘")

    if get_input("\n   Append to ~/.bashrc? (y/N): ", default="n").lower() == "y":
        bashrc = Path.home() / ".bashrc"
        lines = [f'export {k}="{v}"' for k, v in creds.items() if v]

        with open(bashrc, "a") as f:
            f.write("\n# AlphaScout Credentials\n")
            f.write("\n".join(lines) + "\n")

        print(f"   ✅ Added to {bashrc}")
        print("   Run: source ~/.bashrc")


def main():
    print_banner()

    creds = load_credentials()

    if creds:
        print("\n⚠️  Existing credentials found. Press Enter to keep, or type new values.\n")

    creds = setup_llm_keys(creds)
    creds = setup_zerodha(creds)
    creds = setup_telegram(creds)
    creds = setup_capital(creds)

    save_credentials(creds)
    export_to_env(creds)

    print("\n" + "="*70)
    print("✅ SETUP COMPLETE!")
    print("="*70)
    print(f"\nEncrypted credentials: {CRED_FILE}")
    print(f"Encryption key:        {KEY_FILE}")
    print("\nTo test:")
    print("  python -c \"from src.config import validate_api_keys; import json; print(json.dumps(validate_api_keys(), indent=2))\"")
    print("\n" + "="*70)


if __name__ == "__main__":
    main()