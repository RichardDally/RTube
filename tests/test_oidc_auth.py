import pytest
from unittest.mock import patch, MagicMock
import httpx

from rtube.services.oidc_auth import generate_client_secrets, OIDCConfig

@pytest.fixture
def mock_oidc_config():
    return OIDCConfig(
        enabled=True,
        client_id="test_client_id",
        client_secret="test_client_secret",
        discovery_url="https://example.com/.well-known/openid-configuration",
        scopes=["openid", "profile", "email"],
        username_claim="preferred_username"
    )

def test_generate_client_secrets_success(mock_oidc_config):
    discovery_doc = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
        "introspection_endpoint": "https://example.com/introspect",
        "issuer": "https://example.com"
    }

    with patch("rtube.services.oidc_auth.httpx.Client") as mock_client_class:
        mock_client_instance = mock_client_class.return_value.__enter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = discovery_doc
        mock_response.raise_for_status.return_value = None
        mock_client_instance.get.return_value = mock_response

        secrets = generate_client_secrets(mock_oidc_config, "http://localhost/callback")

        mock_client_instance.get.assert_called_once_with("https://example.com/.well-known/openid-configuration")
        
        assert secrets == {
            "web": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "auth_uri": "https://example.com/auth",
                "token_uri": "https://example.com/token",
                "userinfo_uri": "https://example.com/userinfo",
                "token_introspection_uri": "https://example.com/introspect",
                "issuer": "https://example.com",
                "redirect_uris": ["http://localhost/callback"],
            }
        }

def test_generate_client_secrets_missing_endpoints(mock_oidc_config, caplog):
    discovery_doc = {
        "userinfo_endpoint": "https://example.com/userinfo",
        "issuer": "https://example.com"
    }

    with patch("rtube.services.oidc_auth.httpx.Client") as mock_client_class:
        mock_client_instance = mock_client_class.return_value.__enter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = discovery_doc
        mock_response.raise_for_status.return_value = None
        mock_client_instance.get.return_value = mock_response

        secrets = generate_client_secrets(mock_oidc_config, "http://localhost/callback")

        assert secrets["web"]["auth_uri"] is None
        assert secrets["web"]["token_uri"] is None
        assert "Discovery document is missing required endpoints" in caplog.text

def test_generate_client_secrets_http_error(mock_oidc_config):
    with patch("rtube.services.oidc_auth.httpx.Client") as mock_client_class:
        mock_client_instance = mock_client_class.return_value.__enter__.return_value
        mock_client_instance.get.side_effect = httpx.HTTPError("Network error")

        with pytest.raises(RuntimeError, match="Could not load OIDC provider configuration"):
            generate_client_secrets(mock_oidc_config, "http://localhost/callback")
