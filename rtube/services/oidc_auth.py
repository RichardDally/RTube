"""
OpenID Connect (OIDC) Authentication Service for RTube using Flask-OIDC.

Provides OIDC authentication as an alternative to local authentication.
Supports any OIDC-compliant identity provider (Keycloak, Authentik, Azure AD, Okta, etc.).
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def generate_client_secrets(config: OIDCConfig, redirect_uri: str) -> dict[str, Any]:
    """Generate the client_secrets.json structure for Flask-OIDC.

    Args:
        config: OIDC configuration.
        redirect_uri: The redirect URI for the OIDC callback.

    Returns:
        Dictionary structure compatible with Flask-OIDC client_secrets.
    """
    return {
        "web": {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "auth_uri": f"{config.discovery_url.replace('/.well-known/openid-configuration', '')}/protocol/openid-connect/auth",
            "token_uri": f"{config.discovery_url.replace('/.well-known/openid-configuration', '')}/protocol/openid-connect/token",
            "userinfo_uri": f"{config.discovery_url.replace('/.well-known/openid-configuration', '')}/protocol/openid-connect/userinfo",
            "issuer": config.discovery_url.replace("/.well-known/openid-configuration", ""),
            "redirect_uris": [redirect_uri],
        }
    }


def write_client_secrets_file(config: OIDCConfig, instance_path: str, redirect_uri: str) -> str:
    """Write the client_secrets.json file for Flask-OIDC.

    Args:
        config: OIDC configuration.
        instance_path: Flask instance path.
        redirect_uri: The redirect URI for the OIDC callback.

    Returns:
        Path to the generated client_secrets.json file.
    """
    secrets = generate_client_secrets(config, redirect_uri)
    secrets_path = Path(instance_path) / "client_secrets.json"
    secrets_path.parent.mkdir(parents=True, exist_ok=True)

    with open(secrets_path, "w") as f:
        json.dump(secrets, f, indent=2)

    logger.info(f"OIDC client secrets written to {secrets_path}")
    return str(secrets_path)


def configure_flask_oidc(app, config: OIDCConfig) -> None:
    """Configure Flask-OIDC for the application.

    Args:
        app: Flask application instance.
        config: OIDC configuration.
    """
    from flask_oidc import OpenIDConnect

    # Generate redirect URI
    # Note: This will be updated when the app context is available
    redirect_uri = os.environ.get(
        "RTUBE_OIDC_REDIRECT_URI",
        "http://127.0.0.1:5000/auth/oidc/callback"
    )

    # Write client secrets file
    secrets_path = write_client_secrets_file(config, app.instance_path, redirect_uri)

    # Configure Flask-OIDC
    app.config["OIDC_CLIENT_SECRETS"] = secrets_path
    app.config["OIDC_SCOPES"] = config.scopes
    app.config["OIDC_INTROSPECTION_AUTH_METHOD"] = "client_secret_post"
    app.config["OIDC_TOKEN_TYPE_HINT"] = "access_token"

    # Store config for later use
    app.config["OIDC_CONFIG"] = config
    app.config["OIDC_ENABLED"] = True

    # Initialize Flask-OIDC
    oidc = OpenIDConnect(app)
    app.config["OIDC_INSTANCE"] = oidc

    logger.info("Flask-OIDC configured successfully")
