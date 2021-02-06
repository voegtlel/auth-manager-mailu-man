from typing import Optional

from pydantic import BaseSettings


class Settings(BaseSettings):
    hostname: str = "::1"
    port: int = 25

    mail_storage: str = 'mails'

    mailu_oauth_url: Optional[str] = 'http://localhost:8000'
    mailu_oauth_client_id: Optional[str] = 'mail'
    mailu_oauth_client_secret: Optional[str]

    frontend_base_url: str = 'http://127.0.0.1:4200'

    default_language: str = 'en_us'

    postfix_address: str = "smtp"
    dovecot_address: str = "dovecot"


config = Settings()
