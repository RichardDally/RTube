"""
OpenID Connect (OIDC) Authentication Service for RTube.

Provides OIDC authentication as an alternative to local authentication.
Supports any OIDC-compliant identity provider (Keycloak, Azure AD, Okta, etc.).
"""

import logging
import secrets
from dataclasses import dataclass

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import jwt

logger = logging.getLogger(__name__)


@dataclass
class OIDCConfig:
    """Configuration for OIDC authentication."""

    client_id: str
    client_secret: str
    discovery_url: str
    scopes: list[str]
    username_claim: str

    @classmethod
    def from_env(cls, env: dict) -> "OIDCConfig | None":
        """Create OIDCConfig from environment variables.

        Returns None if OIDC is not enabled.
        """
        if env.get("RTUBE_OIDC_ENABLED", "").lower() not in ("true", "1", "yes"):
            return None

        client_id = env.get("RTUBE_OIDC_CLIENT_ID", "")
        client_secret = env.get("RTUBE_OIDC_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            logger.warning("OIDC enabled but client_id or client_secret not configured")
            return None

        scopes_str = env.get("RTUBE_OIDC_SCOPES", "openid profile email")
        scopes = [s.strip() for s in scopes_str.split() if s.strip()]

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            discovery_url=env.get("RTUBE_OIDC_DISCOVERY_URL", ""),
            scopes=scopes,
            username_claim=env.get("RTUBE_OIDC_USERNAME_CLAIM", "preferred_username"),
        )


class OIDCAuthService:
    """Service for authenticating users via OpenID Connect."""

    def __init__(self, config: OIDCConfig):
        """Initialize the OIDC authentication service.

        Args:
            config: OIDC configuration settings.
        """
        self.config = config
        self._metadata = None
        self._jwks = None

    def _fetch_metadata(self) -> dict | None:
        """Fetch and cache the OIDC discovery metadata."""
        if self._metadata is not None:
            return self._metadata

        if not self.config.discovery_url:
            logger.error("OIDC discovery URL not configured")
            return None

        try:
            response = requests.get(self.config.discovery_url, timeout=10)
            response.raise_for_status()
            self._metadata = response.json()
            return self._metadata
        except Exception as e:
            logger.error(f"Failed to fetch OIDC metadata: {e}")
            return None

    def _fetch_jwks(self) -> dict | None:
        """Fetch and cache the JWKS for token validation."""
        if self._jwks is not None:
            return self._jwks

        metadata = self._fetch_metadata()
        if not metadata:
            return None

        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            logger.error("OIDC metadata missing jwks_uri")
            return None

        try:
            response = requests.get(jwks_uri, timeout=10)
            response.raise_for_status()
            self._jwks = response.json()
            return self._jwks
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            return None

    def get_authorization_url(self, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
        """Generate the authorization URL to redirect the user to.

        Args:
            redirect_uri: The callback URL for the OIDC provider to redirect to.
            state: Optional state parameter for CSRF protection.
                   If not provided, a random state will be generated.

        Returns:
            Tuple of (authorization_url, state).
        """
        metadata = self._fetch_metadata()
        if not metadata:
            raise RuntimeError("Unable to fetch OIDC metadata")

        authorization_endpoint = metadata.get("authorization_endpoint")
        if not authorization_endpoint:
            raise RuntimeError("OIDC metadata missing authorization_endpoint")

        if state is None:
            state = secrets.token_urlsafe(32)

        session = OAuth2Session(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            scope=" ".join(self.config.scopes),
            redirect_uri=redirect_uri,
        )

        url, _ = session.create_authorization_url(
            authorization_endpoint,
            state=state,
        )

        return url, state

    def handle_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        expected_state: str | None = None,
    ) -> dict:
        """Handle the OIDC callback and exchange the code for tokens.

        Args:
            code: The authorization code from the callback.
            state: The state parameter from the callback.
            redirect_uri: The callback URL (must match the one used in authorization).
            expected_state: The expected state for CSRF validation.

        Returns:
            Dictionary with user information including 'sub' and username.

        Raises:
            ValueError: If state validation fails.
            RuntimeError: If token exchange or userinfo fetch fails.
        """
        if expected_state and state != expected_state:
            raise ValueError("Invalid state parameter - possible CSRF attack")

        metadata = self._fetch_metadata()
        if not metadata:
            raise RuntimeError("Unable to fetch OIDC metadata")

        token_endpoint = metadata.get("token_endpoint")
        if not token_endpoint:
            raise RuntimeError("OIDC metadata missing token_endpoint")

        session = OAuth2Session(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            redirect_uri=redirect_uri,
        )

        try:
            token = session.fetch_token(
                token_endpoint,
                code=code,
            )
        except Exception as e:
            logger.error(f"Failed to exchange authorization code: {e}")
            raise RuntimeError(f"Token exchange failed: {e}") from e

        # Get user info from ID token or userinfo endpoint
        userinfo = self._get_userinfo(session, token, metadata)

        # Extract the username using the configured claim
        sub = userinfo.get("sub")
        if not sub:
            raise RuntimeError("OIDC response missing 'sub' claim")

        username = userinfo.get(self.config.username_claim)
        if not username:
            # Fallback to other common claims
            username = userinfo.get("preferred_username") or userinfo.get("email") or sub

        return {
            "sub": sub,
            "username": username,
            "email": userinfo.get("email"),
            "name": userinfo.get("name"),
            "raw_userinfo": userinfo,
        }

    def _get_userinfo(self, session: OAuth2Session, token: dict, metadata: dict) -> dict:
        """Get user information from ID token or userinfo endpoint.

        Args:
            session: The OAuth2 session.
            token: The token response.
            metadata: The OIDC metadata.

        Returns:
            Dictionary with user information.
        """
        # First, try to get info from the ID token
        id_token = token.get("id_token")
        if id_token:
            try:
                # Decode without verification for now (validation done by authlib)
                claims = jwt.decode(id_token, self._fetch_jwks())
                if claims:
                    return dict(claims)
            except Exception as e:
                logger.warning(f"Failed to decode ID token: {e}")

        # Fallback to userinfo endpoint
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if userinfo_endpoint:
            try:
                response = session.get(userinfo_endpoint)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Failed to fetch userinfo: {e}")

        # Return what we have from the token response
        return token

    def test_connection(self) -> bool:
        """Test the OIDC configuration by fetching metadata.

        Returns:
            True if metadata fetch successful, False otherwise.
        """
        return self._fetch_metadata() is not None
