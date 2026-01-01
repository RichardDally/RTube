"""
Tests for OIDC authentication.
"""
import os
from unittest.mock import Mock

import pytest

from rtube.models import db
from rtube.models_auth import User
from rtube.services.oidc_auth import OIDCAuthService, OIDCConfig


class TestOIDCConfig:
    """Tests for OIDC configuration."""

    def test_from_env_disabled(self):
        """Test that OIDC is disabled by default."""
        config = OIDCConfig.from_env({})
        assert config is None

    def test_from_env_enabled(self):
        """Test OIDC configuration from environment variables."""
        env = {
            "RTUBE_OIDC_ENABLED": "true",
            "RTUBE_OIDC_CLIENT_ID": "my-client-id",
            "RTUBE_OIDC_CLIENT_SECRET": "my-client-secret",
            "RTUBE_OIDC_DISCOVERY_URL": "https://idp.example.com/.well-known/openid-configuration",
            "RTUBE_OIDC_SCOPES": "openid profile email",
            "RTUBE_OIDC_USERNAME_CLAIM": "preferred_username",
        }
        config = OIDCConfig.from_env(env)

        assert config is not None
        assert config.client_id == "my-client-id"
        assert config.client_secret == "my-client-secret"
        assert config.discovery_url == "https://idp.example.com/.well-known/openid-configuration"
        assert config.scopes == ["openid", "profile", "email"]
        assert config.username_claim == "preferred_username"

    def test_from_env_missing_credentials(self):
        """Test OIDC configuration with missing credentials returns None."""
        env = {
            "RTUBE_OIDC_ENABLED": "true",
            # Missing client_id and client_secret
        }
        config = OIDCConfig.from_env(env)
        assert config is None

    def test_from_env_defaults(self):
        """Test OIDC configuration with minimal environment variables."""
        env = {
            "RTUBE_OIDC_ENABLED": "true",
            "RTUBE_OIDC_CLIENT_ID": "my-client",
            "RTUBE_OIDC_CLIENT_SECRET": "my-secret",
        }
        config = OIDCConfig.from_env(env)

        assert config is not None
        assert config.scopes == ["openid", "profile", "email"]
        assert config.username_claim == "preferred_username"


class TestOIDCAuthService:
    """Tests for OIDC authentication service."""

    def test_get_authorization_url(self):
        """Test generation of authorization URL."""
        config = OIDCConfig(
            client_id="test-client",
            client_secret="test-secret",
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            scopes=["openid", "profile"],
            username_claim="preferred_username",
        )
        service = OIDCAuthService(config)

        # Mock the metadata fetch
        mock_metadata = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }
        service._metadata = mock_metadata

        url, state = service.get_authorization_url("https://rtube.example.com/auth/oidc/callback")

        assert "https://idp.example.com/authorize" in url
        assert "client_id=test-client" in url
        assert "redirect_uri=" in url
        assert state is not None
        assert len(state) > 20  # State should be reasonably long

    def test_get_authorization_url_with_custom_state(self):
        """Test generation of authorization URL with custom state."""
        config = OIDCConfig(
            client_id="test-client",
            client_secret="test-secret",
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            scopes=["openid"],
            username_claim="sub",
        )
        service = OIDCAuthService(config)

        mock_metadata = {
            "authorization_endpoint": "https://idp.example.com/authorize",
        }
        service._metadata = mock_metadata

        custom_state = "my-custom-state-123"
        url, state = service.get_authorization_url(
            "https://rtube.example.com/callback",
            state=custom_state
        )

        assert state == custom_state
        assert f"state={custom_state}" in url

    def test_fetch_metadata_cached(self):
        """Test that metadata is cached after first fetch."""
        config = OIDCConfig(
            client_id="test-client",
            client_secret="test-secret",
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            scopes=["openid"],
            username_claim="sub",
        )
        service = OIDCAuthService(config)

        # Pre-set metadata to simulate successful fetch
        test_metadata = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }
        service._metadata = test_metadata

        # Should return cached metadata without making HTTP request
        metadata = service._fetch_metadata()

        assert metadata is not None
        assert metadata["authorization_endpoint"] == "https://idp.example.com/authorize"

    def test_test_connection_success(self):
        """Test connection test with valid metadata."""
        config = OIDCConfig(
            client_id="test-client",
            client_secret="test-secret",
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            scopes=["openid"],
            username_claim="sub",
        )
        service = OIDCAuthService(config)

        # Pre-set metadata to simulate successful fetch
        service._metadata = {"authorization_endpoint": "https://idp.example.com/authorize"}

        assert service.test_connection() is True

    def test_test_connection_failure(self):
        """Test connection test without metadata."""
        config = OIDCConfig(
            client_id="test-client",
            client_secret="test-secret",
            discovery_url="",  # No URL
            scopes=["openid"],
            username_claim="sub",
        )
        service = OIDCAuthService(config)

        assert service.test_connection() is False


class TestOIDCLoginRoute:
    """Tests for OIDC login functionality in routes."""

    @pytest.fixture
    def oidc_app(self):
        """Create app with OIDC enabled (mocked)."""
        os.environ["TESTING"] = "true"

        from rtube.app import create_app

        mock_oidc_service = Mock()
        mock_oidc_service.get_authorization_url = Mock(
            return_value=("https://idp.example.com/authorize?client_id=test", "test-state")
        )

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }

        app = create_app(test_config=test_config)

        app.config["OIDC_ENABLED"] = True
        app.config["OIDC_SERVICE"] = mock_oidc_service

        yield app, mock_oidc_service

        with app.app_context():
            db.session.remove()

    def test_oidc_login_redirects_to_provider(self, oidc_app):
        """Test that OIDC login redirects to the IdP."""
        app, mock_oidc_service = oidc_app

        client = app.test_client()

        response = client.get('/auth/oidc/login')

        assert response.status_code == 302
        assert 'idp.example.com' in response.location

    def test_oidc_login_stores_state_in_session(self, oidc_app):
        """Test that OIDC login stores state in session."""
        app, mock_oidc_service = oidc_app

        with app.test_client() as client:
            client.get('/auth/oidc/login')

            with client.session_transaction() as sess:
                assert 'oidc_state' in sess
                assert sess['oidc_state'] == 'test-state'

    def test_oidc_callback_without_code_fails(self, oidc_app):
        """Test OIDC callback without authorization code."""
        app, mock_oidc_service = oidc_app

        client = app.test_client()

        response = client.get('/auth/oidc/callback?state=test')

        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_oidc_callback_with_error(self, oidc_app):
        """Test OIDC callback with error from provider."""
        app, mock_oidc_service = oidc_app

        client = app.test_client()

        response = client.get('/auth/oidc/callback?error=access_denied&error_description=User%20denied')

        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_login_page_shows_oidc_button(self, oidc_app):
        """Test that login page shows OIDC button when enabled."""
        app, mock_oidc_service = oidc_app

        client = app.test_client()

        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Sign in with SSO (OIDC)' in response.data


class TestOIDCUserCreation:
    """Tests for OIDC user auto-creation."""

    @pytest.fixture
    def oidc_app_with_callback(self):
        """Create app with OIDC enabled and mocked callback."""
        os.environ["TESTING"] = "true"

        from rtube.app import create_app

        mock_oidc_service = Mock()
        mock_oidc_service.get_authorization_url = Mock(
            return_value=("https://idp.example.com/authorize", "test-state")
        )
        mock_oidc_service.handle_callback = Mock(return_value={
            'sub': 'oidc-user-12345',
            'username': 'oidcuser',
            'email': 'oidcuser@example.com',
            'name': 'OIDC User',
        })

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }

        app = create_app(test_config=test_config)

        app.config["OIDC_ENABLED"] = True
        app.config["OIDC_SERVICE"] = mock_oidc_service

        yield app, mock_oidc_service

        with app.app_context():
            db.session.remove()

    def test_oidc_callback_creates_user(self, oidc_app_with_callback):
        """Test that OIDC callback auto-creates user on first login."""
        app, mock_oidc_service = oidc_app_with_callback

        with app.test_client() as client:
            # Set up session state
            with client.session_transaction() as sess:
                sess['oidc_state'] = 'test-state'

            response = client.get('/auth/oidc/callback?code=auth-code&state=test-state')

            assert response.status_code == 302

            # Verify user was created
            with app.app_context():
                user = User.query.filter_by(sso_subject='oidc-user-12345').first()
                assert user is not None
                assert user.auth_type == 'oidc'
                assert user.username == 'oidcuser'

    def test_oidc_callback_existing_user(self, oidc_app_with_callback):
        """Test OIDC callback with existing OIDC user."""
        app, mock_oidc_service = oidc_app_with_callback

        # Create existing user
        with app.app_context():
            user = User(
                username='oidcuser',
                auth_type='oidc',
                sso_subject='oidc-user-12345'
            )
            db.session.add(user)
            db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['oidc_state'] = 'test-state'

            response = client.get('/auth/oidc/callback?code=auth-code&state=test-state')

            assert response.status_code == 302

            # Verify no duplicate user created
            with app.app_context():
                users = User.query.filter_by(sso_subject='oidc-user-12345').all()
                assert len(users) == 1


class TestUserModelOIDC:
    """Tests for User model OIDC-related methods."""

    def test_is_oidc_user(self, app):
        """Test is_oidc_user method."""
        with app.app_context():
            oidc_user = User(username='oidctest', auth_type='oidc', sso_subject='sub-123')
            local_user = User(username='localtest', auth_type='local')

            assert oidc_user.is_oidc_user() is True
            assert oidc_user.is_sso_user() is True
            assert oidc_user.is_local_user() is False

            assert local_user.is_oidc_user() is False
            assert local_user.is_sso_user() is False
            assert local_user.is_local_user() is True

    def test_oidc_user_check_password_fails(self, app):
        """Test that check_password returns False for OIDC users."""
        with app.app_context():
            oidc_user = User(username='oidctest', auth_type='oidc', sso_subject='sub-123')

            # OIDC users should not be able to use local password check
            assert oidc_user.check_password('anypassword') is False
