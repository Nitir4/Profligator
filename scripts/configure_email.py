"""Privately configure separate Gmail senders; never print or store credentials in source."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
from profligator_api.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", choices=("verification", "reset", "both"), default="both",
                        help="Configure one sender without changing the other")
    purpose = parser.parse_args().purpose
    updates = {}
    senders = []
    if purpose in {"reset", "both"}:
        senders.append(("Password reset", "SMTP"))
        updates["PROFLIGATOR_PASSWORD_RESET_EMAIL_BACKEND"] = "smtp"
    if purpose in {"verification", "both"}:
        senders.append(("Account verification", "VERIFICATION_SMTP"))
        updates["PROFLIGATOR_VERIFICATION_EMAIL_BACKEND"] = "smtp"
    for label, prefix in senders:
        print(f"{label} sender")
        default = "reset@example.com" if prefix == "SMTP" else "verification@example.com"
        email = input(f"Gmail address [{default}]: ").strip() or default
        password = getpass("Gmail app password (hidden): ").replace(" ", "")
        if not email or not password or any(c in email + password for c in '\r\n\x00'):
            raise SystemExit("A sender address and app password are required. No changes made.")
        updates.update({f"PROFLIGATOR_{prefix}_HOST": "smtp.gmail.com",
            f"PROFLIGATOR_{prefix}_PORT": "587", f"PROFLIGATOR_{prefix}_SECURITY": "starttls",
            f"PROFLIGATOR_{prefix}_USERNAME": email, f"PROFLIGATOR_{prefix}_PASSWORD": password,
            f"PROFLIGATOR_{prefix}_FROM_EMAIL": email})
    path = ROOT / "apps/api/.env"
    original = path.read_text() if path.exists() else ""
    # Validate before changing the existing environment. Credentials are never printed.
    from pydantic import SecretStr
    typed = {k.removeprefix("PROFLIGATOR_").lower(): SecretStr(v) if k.endswith("_PASSWORD") else v for k, v in updates.items()}
    try:
        Settings(**typed)
    except Exception:
        raise SystemExit("Email configuration failed validation. Check the sender addresses and existing app settings. No changes made.") from None
    import json
    lines = [line for line in original.splitlines() if line.partition("=")[0].strip().removeprefix("export ") not in updates]
    lines += [f"{key}={json.dumps(value)}" for key, value in updates.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".email-setup-", dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as out:
            out.write('\n'.join(lines) + '\n')
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Saved selected sender settings to apps/api/.env with owner-only permissions. Restart the API. No messages sent.")


if __name__ == "__main__":
    main()
