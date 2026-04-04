"""
OpenID Connect (OIDC) Authentication Service for RTube using Flask-OIDC.

Provides OIDC authentication as an alternative to local authentication.
Supports any OIDC-compliant identity provider (Keycloak, Authentik, Azure AD, Okta, etc.).
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OIDCConfig:
    """Configuration for OIDC authentication."""

    enabled: bool
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
        discovery_url = env.get("RTUBE_OIDC_DISCOVERY_URL", "")

        if not client_id or not client_secret or not discovery_url:
            logger.warning(
                "OIDC enabled but client_id, client_secret, or discovery_url not configured"
            )
            return None

        scopes_str = env.get("RTUBE_OIDC_SCOPES", "openid profile email")
        scopes = [s.strip() for s in scopes_str.split() if s.strip()]

        return cls(
            enabled=True,
            client_id=client_id,
            client_secret=client_secret,
            discovery_url=discovery_url,
            scopes=scopes,
            username_claim=env.get("RTUBE_OIDC_USERNAME_CLAIM", "preferred_username"),
        )


def configure_flask_oidc(app, config: OIDCConfig) -> None:
    """Configure Authlib OAuth for the application.

    Args:
        app: Flask application instance.
        config: OIDC configuration.
    """
    from authlib.integrations.flask_client import OAuth

    # We need a proper secret key for session management, required by Authlib
    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "dev-secret-key"
        else:
            raise RuntimeError("A SECRET_KEY must be configured to use OIDC authentication.")

    oauth = OAuth(app)
    
    # Store config for later use
    app.config["OIDC_CONFIG"] = config
    app.config["OIDC_ENABLED"] = True

    client_kwargs = {
        'scope': ' '.join(config.scopes),
    }

    # Register OIDC client
    oauth.register(
        name='oidc',
        client_id=config.client_id,
        client_secret=config.client_secret,
        server_metadata_url=config.discovery_url,
        client_kwargs=client_kwargs,
    )
    
    app.config["OAUTH_INSTANCE"] = oauth
    app.config["OIDC_INSTANCE"] = oauth.oidc
    logger.info("Authlib OIDC configured successfully")
