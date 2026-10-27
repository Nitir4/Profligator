"""Send two explicitly requested SMTP delivery-check messages to one inbox."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api/src'))
from pydantic import EmailStr, TypeAdapter
from profligator_api.config import Settings
from profligator_api.password_recovery import RecoveryMailer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipient',required=True,help='Inbox you authorize to receive both test messages')
    args=parser.parse_args()
    try:
        recipient=str(TypeAdapter(EmailStr).validate_python(args.recipient))
        settings=Settings()
    except Exception:
        raise SystemExit('Invalid recipient or email configuration. No messages sent.') from None
    if settings.verification_email_backend!='smtp' or settings.password_reset_email_backend!='smtp':
        raise SystemExit('Configure both SMTP senders first with scripts/configure_email.py. No messages sent.')
    for purpose,config in [('verification',settings.verification_mail_settings()),('password reset',settings)]:
        try:
            RecoveryMailer(config).send(recipient,f'Profligator {purpose} delivery check',
                f'This is the requested Profligator {purpose} sender check.\n\n'
                'No account state was changed. Confirm this message reached your inbox or spam folder.\n')
        except Exception as error:
            raise SystemExit(f'{purpose.capitalize()} sender failed ({type(error).__name__}). Credentials and SMTP response omitted.') from None
        print(f'{purpose.capitalize()} sender: SMTP accepted the message. Inbox delivery still needs confirmation.')


if __name__=='__main__':
    main()
