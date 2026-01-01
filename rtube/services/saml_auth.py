"""
SAML 2.0 Authentication Service for RTube.

Provides SAML authentication as an alternative to local authentication.
Supports any SAML 2.0 compliant identity provider (ADFS, Okta, Shibboleth, etc.).
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SAMLConfig:
    """Configuration for SAML authentication."""

    idp_entity_id: str
    idp_sso_url: str
    idp_cert: str
    sp_entity_id: str
    username_attribute: str
    email_attribute: str
    name_attribute: str

    @classmethod
    def from_env(cls, env: dict) -> "SAMLConfig | None":
        """Create SAMLConfig from environment variables.

        Returns None if SAML is not enabled.
        """
        if env.get("RTUBE_SAML_ENABLED", "").lower() not in ("true", "1", "yes"):
            return None

        idp_entity_id = env.get("RTUBE_SAML_IDP_ENTITY_ID", "")
        idp_sso_url = env.get("RTUBE_SAML_IDP_SSO_URL", "")

        if not idp_entity_id or not idp_sso_url:
            logger.warning("SAML enabled but IdP configuration incomplete")
            return None

        # Load IdP certificate from file or environment
        idp_cert = ""
        cert_file = env.get("RTUBE_SAML_IDP_CERT_FILE", "")
        if cert_file and Path(cert_file).exists():
            idp_cert = Path(cert_file).read_text().strip()
        else:
            idp_cert = env.get("RTUBE_SAML_IDP_CERT", "")

        if not idp_cert:
            logger.warning("SAML enabled but IdP certificate not configured")
            return None

        return cls(
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_cert=idp_cert,
            sp_entity_id=env.get("RTUBE_SAML_SP_ENTITY_ID", ""),
            username_attribute=env.get("RTUBE_SAML_USERNAME_ATTRIBUTE", "uid"),
            email_attribute=env.get("RTUBE_SAML_EMAIL_ATTRIBUTE", "email"),
            name_attribute=env.get("RTUBE_SAML_NAME_ATTRIBUTE", "displayName"),
        )


class SAMLAuthService:
    """Service for authenticating users via SAML 2.0."""

    def __init__(self, config: SAMLConfig):
        """Initialize the SAML authentication service.

        Args:
            config: SAML configuration settings.
        """
        self.config = config

    def _get_saml_settings(self, request_url: str, acs_url: str) -> dict:
        """Build the python3-saml settings dictionary.

        Args:
            request_url: The base URL of the application.
            acs_url: The Assertion Consumer Service URL.

        Returns:
            Settings dictionary for python3-saml.
        """
        parsed = urlparse(request_url)
        sp_entity_id = self.config.sp_entity_id or f"{parsed.scheme}://{parsed.netloc}"

        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": sp_entity_id,
                "assertionConsumerService": {
                    "url": acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
            },
            "idp": {
                "entityId": self.config.idp_entity_id,
                "singleSignOnService": {
                    "url": self.config.idp_sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self._clean_certificate(self.config.idp_cert),
            },
            "security": {
                "nameIdEncrypted": False,
                "authnRequestsSigned": False,
                "logoutRequestSigned": False,
                "logoutResponseSigned": False,
                "signMetadata": False,
                "wantMessagesSigned": False,
                "wantAssertionsSigned": True,
                "wantNameIdEncrypted": False,
                "wantAttributeStatement": True,
                "requestedAuthnContext": False,
            },
        }

    def _clean_certificate(self, cert: str) -> str:
        """Clean certificate by removing PEM headers and whitespace.

        Args:
            cert: The certificate string (PEM format).

        Returns:
            Cleaned certificate string without headers.
        """
        lines = cert.strip().split("\n")
        # Remove BEGIN/END lines and join
        clean_lines = [
            line.strip()
            for line in lines
            if not line.startswith("-----") and line.strip()
        ]
        return "".join(clean_lines)

    def _prepare_request(self, request) -> dict:
        """Prepare request data for python3-saml.

        Args:
            request: Flask request object.

        Returns:
            Dictionary with request data for python3-saml.
        """
        url_data = urlparse(request.url)
        return {
            "https": "on" if request.scheme == "https" else "off",
            "http_host": request.host,
            "server_port": url_data.port or (443 if request.scheme == "https" else 80),
            "script_name": request.path,
            "get_data": request.args.copy(),
            "post_data": request.form.copy(),
        }

    def get_login_url(self, request, return_to: str | None = None) -> str:
        """Generate the SAML login URL to redirect the user to.

        Args:
            request: Flask request object.
            return_to: Optional URL to redirect to after login.

        Returns:
            The SAML AuthnRequest URL.
        """
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        acs_url = f"{request.scheme}://{request.host}/auth/saml/acs"
        settings = self._get_saml_settings(request.url, acs_url)
        req = self._prepare_request(request)

        auth = OneLogin_Saml2_Auth(req, settings)
        return auth.login(return_to=return_to)

    def process_response(self, request) -> dict:
        """Process the SAML response from the IdP.

        Args:
            request: Flask request object containing the SAML response.

        Returns:
            Dictionary with user information.

        Raises:
            ValueError: If the SAML response is invalid.
        """
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        acs_url = f"{request.scheme}://{request.host}/auth/saml/acs"
        settings = self._get_saml_settings(request.url, acs_url)
        req = self._prepare_request(request)

        auth = OneLogin_Saml2_Auth(req, settings)
        auth.process_response()

        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            logger.error(f"SAML authentication failed: {errors}, reason: {error_reason}")
            raise ValueError(f"SAML authentication failed: {error_reason or errors}")

        if not auth.is_authenticated():
            raise ValueError("SAML authentication failed: user not authenticated")

        # Get NameID (unique identifier from IdP)
        name_id = auth.get_nameid()
        if not name_id:
            raise ValueError("SAML response missing NameID")

        # Get attributes
        attributes = auth.get_attributes()

        # Extract username using configured attribute
        username = None
        username_values = attributes.get(self.config.username_attribute, [])
        if username_values:
            username = username_values[0]
        else:
            # Fallback to NameID
            username = name_id

        # Extract email
        email = None
        email_values = attributes.get(self.config.email_attribute, [])
        if email_values:
            email = email_values[0]

        # Extract display name
        name = None
        name_values = attributes.get(self.config.name_attribute, [])
        if name_values:
            name = name_values[0]

        return {
            "name_id": name_id,
            "username": username,
            "email": email,
            "name": name,
            "attributes": attributes,
            "session_index": auth.get_session_index(),
        }

    def get_metadata(self, request) -> str:
        """Generate SP metadata XML.

        Args:
            request: Flask request object.

        Returns:
            SP metadata as XML string.
        """
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        acs_url = f"{request.scheme}://{request.host}/auth/saml/acs"
        settings = self._get_saml_settings(request.url, acs_url)
        req = self._prepare_request(request)

        auth = OneLogin_Saml2_Auth(req, settings)
        saml_settings = auth.get_settings()
        metadata = saml_settings.get_sp_metadata()

        errors = saml_settings.validate_metadata(metadata)
        if errors:
            logger.warning(f"SP metadata validation errors: {errors}")

        return metadata

    def test_connection(self) -> bool:
        """Test the SAML configuration.

        Returns:
            True if configuration is valid, False otherwise.
        """
        try:
            # Just verify we can build settings without error
            self._get_saml_settings("https://example.com", "https://example.com/acs")
            return True
        except Exception as e:
            logger.error(f"SAML configuration test failed: {e}")
            return False
