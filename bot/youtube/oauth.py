"""
Authentication and OAuth for YouTube API.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']


class YouTubeAuth:
    """Handles OAuth 2.0 authentication for the YouTube Data API."""

    def __init__(self, client_id: Optional[str], client_secret: Optional[str], token_path: Path):
        """
        Initialize the YouTube authenticator.

        Args:
            client_id: OAuth 2.0 Client ID.
            client_secret: OAuth 2.0 Client Secret.
            token_path: Path to save/load the token file.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = token_path

    @property
    def is_configured(self) -> bool:
        """Check if client_id and client_secret are provided."""
        return bool(self.client_id and self.client_secret)

    def load_credentials(self) -> Optional[Credentials]:
        """
        Load credentials from the token file if it exists.

        Returns:
            The loaded Credentials object, or None if the file doesn't exist.
        """
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                logger.info("Loaded YouTube credentials from token file.")
                return creds
            except Exception as e:
                logger.error(f"Failed to load YouTube credentials from file: {e}")
                return None
        return None

    def save_credentials(self, creds: Credentials) -> None:
        """
        Save credentials to the token file with restricted permissions.

        Args:
            creds: The Credentials object to save.
        """
        try:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w', encoding='utf-8') as token_file:
                token_file.write(creds.to_json())
            
            # Restrict permissions on Unix-like systems
            if os.name == 'posix':
                os.chmod(self.token_path, 0o600)
            
            logger.info("Saved YouTube credentials to token file.")
        except Exception as e:
            logger.error(f"Failed to save YouTube credentials: {e}")

    def refresh_if_needed(self, creds: Credentials) -> Optional[Credentials]:
        """
        Refresh expired tokens if possible.

        Args:
            creds: The Credentials object to refresh.

        Returns:
            The refreshed Credentials, or None if refresh failed.
        """
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired YouTube access token.")
                creds.refresh(Request())
                self.save_credentials(creds)
                return creds
            except Exception as e:
                logger.error(f"Failed to refresh YouTube token: {e}")
                return None
        return creds

    def run_auth_flow(self) -> Credentials:
        """
        Run the interactive OAuth flow to obtain new credentials.
        This will open a browser window for the user to authenticate.

        Returns:
            The newly obtained Credentials.
        """
        if not self.is_configured:
            raise ValueError("YouTube client_id and client_secret are not configured.")

        # Create temporary client secrets file format expected by InstalledAppFlow
        client_config = {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }

        try:
            logger.info("Starting YouTube OAuth flow...")
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            self.save_credentials(creds)
            return creds
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            raise

    def create_from_tokens(self, access_token: str, refresh_token: str) -> Credentials:
        """
        Create credentials directly from token values.

        Args:
            access_token: The OAuth access token.
            refresh_token: The OAuth refresh token.

        Returns:
            A new Credentials object.
        """
        if not self.is_configured:
            raise ValueError("YouTube client_id and client_secret are not configured.")
            
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=SCOPES
        )
        self.save_credentials(creds)
        return creds
