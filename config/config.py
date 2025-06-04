# Configuration management
## config/config.py
#!/usr/bin/env python3
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    client_id: str = os.getenv("ML_CLIENT_ID")
    client_secret: str = os.getenv("ML_CLIENT_SECRET")
    redirect_uri: str = os.getenv("ML_REDIRECT_URI")
    timeout: int = int(os.getenv("API_TIMEOUT", 30))
    rate_limit: int = int(os.getenv("RATE_LIMIT", 100))

    # API URLs
    api_url: str = "https://api.mercadolibre.com"
    auth_url: str = "https://auth.mercadolivre.com.br"

    # Files
    token_file: str = "ml_tokens.json"

    # Fallback tokens
    fallback_access: str = os.getenv("ACCESS_TOKEN")
    fallback_refresh: str = os.getenv("REFRESH_TOKEN")
    fallback_expires: str = os.getenv("TOKEN_EXPIRES")


cfg = Config()
