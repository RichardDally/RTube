import pytest
from unittest.mock import patch, MagicMock
from rtube.services.oidc_auth import configure_flask_oidc, OIDCConfig
from rtube.models_auth import User
import authlib.integrations.flask_client

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

def test_configure_flask_oidc_registers_authlib(app, mock_oidc_config):
    """Test that Authlib is properly configured and attached to the app."""
    with patch("authlib.integrations.flask_client.OAuth") as mock_oauth_class:
        mock_oauth_instance = mock_oauth_class.return_value
        
        configure_flask_oidc(app, mock_oidc_config)
        
        mock_oauth_class.assert_called_once_with(app)
        mock_oauth_instance.register.assert_called_once_with(
            name='oidc',
            client_id="test_client_id",
            client_secret="test_client_secret",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
            client_kwargs={'scope': 'openid profile email'}
        )
        assert app.config["OIDC_CONFIG"] == mock_oidc_config
        assert app.config["OIDC_ENABLED"] is True
        assert app.config["OAUTH_INSTANCE"] == mock_oauth_instance

def test_oidc_login_redirects_to_provider(client, app, mock_oidc_config):
    """Test that /auth/oidc/login redirects to the OIDC provider."""
    configure_flask_oidc(app, mock_oidc_config)
    
    with patch.object(app.config["OAUTH_INSTANCE"].oidc, 'authorize_redirect') as mock_redirect:
        mock_redirect.return_value = "redirect_in_progress"
        
        response = client.get('/auth/oidc/login')
        
        mock_redirect.assert_called_once()
        # Since it returns our string literal mock
        assert response.status_code == 200

def test_oidc_login_safe_next_url(client, app, mock_oidc_config):
    """Test that /auth/oidc/login only stores safe relative URLs."""
    configure_flask_oidc(app, mock_oidc_config)
    
    with patch.object(app.config["OAUTH_INSTANCE"].oidc, 'authorize_redirect'):
        with client.session_transaction() as sess:
            sess.clear()
        client.get('/auth/oidc/login?next=/some/valid/path')
        with client.session_transaction() as sess:
            assert sess.get('oidc_next') == '/some/valid/path'
            
        with client.session_transaction() as sess:
            sess.clear()
        client.get('/auth/oidc/login?next=http://malicious.com/')
        with client.session_transaction() as sess:
            assert 'oidc_next' not in sess

def test_oidc_callback_success_new_user(client, app, mock_oidc_config):
    """Test successful OIDC callback creating a new user with sanitized username."""
    configure_flask_oidc(app, mock_oidc_config)
    
    mock_token = {
        'userinfo': {
            'sub': '123456789',
            'preferred_username': 'test.user@example.com',
            'email': 'test.user@example.com'
        }
    }
    
    with patch.object(app.config["OAUTH_INSTANCE"].oidc, 'authorize_access_token', return_value=mock_token):
        response = client.get('/auth/oidc/callback')
        
        # Should redirect to index upon successful login
        assert response.status_code == 302
        assert response.headers['Location'] == '/'
        
        # Verify user was created properly
        with app.app_context():
            user = User.query.filter_by(username='test_user').first()
            assert user is not None
            assert user.auth_type == 'sso'
            assert user.role == 'viewer'
