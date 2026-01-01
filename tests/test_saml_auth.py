"""
Tests for SAML authentication.
"""
import os
from unittest.mock import Mock

import pytest

from rtube.models import db
from rtube.models_auth import User
from rtube.services.saml_auth import SAMLAuthService, SAMLConfig


class TestSAMLConfig:
    """Tests for SAML configuration."""

    def test_from_env_disabled(self):
        """Test that SAML is disabled by default."""
        config = SAMLConfig.from_env({})
        assert config is None

    def test_from_env_enabled(self):
        """Test SAML configuration from environment variables."""
        env = {
            "RTUBE_SAML_ENABLED": "true",
            "RTUBE_SAML_IDP_ENTITY_ID": "https://idp.example.com",
            "RTUBE_SAML_IDP_SSO_URL": "https://idp.example.com/sso",
            "RTUBE_SAML_IDP_CERT": "MIIC...certificate...",
            "RTUBE_SAML_SP_ENTITY_ID": "https://rtube.example.com",
            "RTUBE_SAML_USERNAME_ATTRIBUTE": "uid",
        }
        config = SAMLConfig.from_env(env)

        assert config is not None
        assert config.idp_entity_id == "https://idp.example.com"
        assert config.idp_sso_url == "https://idp.example.com/sso"
        assert config.idp_cert == "MIIC...certificate..."
        assert config.sp_entity_id == "https://rtube.example.com"
        assert config.username_attribute == "uid"

    def test_from_env_missing_idp_config(self):
        """Test SAML configuration with missing IdP config returns None."""
        env = {
            "RTUBE_SAML_ENABLED": "true",
            # Missing idp_entity_id and idp_sso_url
        }
        config = SAMLConfig.from_env(env)
        assert config is None

    def test_from_env_missing_cert(self):
        """Test SAML configuration with missing certificate returns None."""
        env = {
            "RTUBE_SAML_ENABLED": "true",
            "RTUBE_SAML_IDP_ENTITY_ID": "https://idp.example.com",
            "RTUBE_SAML_IDP_SSO_URL": "https://idp.example.com/sso",
            # Missing certificate
        }
        config = SAMLConfig.from_env(env)
        assert config is None

    def test_from_env_defaults(self):
        """Test SAML configuration with minimal environment variables."""
        env = {
            "RTUBE_SAML_ENABLED": "true",
            "RTUBE_SAML_IDP_ENTITY_ID": "https://idp.example.com",
            "RTUBE_SAML_IDP_SSO_URL": "https://idp.example.com/sso",
            "RTUBE_SAML_IDP_CERT": "MIIC...certificate...",
        }
        config = SAMLConfig.from_env(env)

        assert config is not None
        assert config.username_attribute == "uid"
        assert config.email_attribute == "email"
        assert config.name_attribute == "displayName"


class TestSAMLAuthService:
    """Tests for SAML authentication service."""

    def test_clean_certificate(self):
        """Test certificate cleaning removes PEM headers."""
        config = SAMLConfig(
            idp_entity_id="https://idp.example.com",
            idp_sso_url="https://idp.example.com/sso",
            idp_cert="-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----",
            sp_entity_id="https://rtube.example.com",
            username_attribute="uid",
            email_attribute="email",
            name_attribute="displayName",
        )
        service = SAMLAuthService(config)

        cleaned = service._clean_certificate(config.idp_cert)
        assert "-----BEGIN" not in cleaned
        assert "-----END" not in cleaned
        assert "MIIC..." in cleaned

    def test_get_saml_settings(self):
        """Test SAML settings generation."""
        config = SAMLConfig(
            idp_entity_id="https://idp.example.com",
            idp_sso_url="https://idp.example.com/sso",
            idp_cert="MIICcertificate",
            sp_entity_id="https://rtube.example.com",
            username_attribute="uid",
            email_attribute="email",
            name_attribute="displayName",
        )
        service = SAMLAuthService(config)

        settings = service._get_saml_settings(
            "https://rtube.example.com/auth/login",
            "https://rtube.example.com/auth/saml/acs"
        )

        assert settings["strict"] is True
        assert settings["idp"]["entityId"] == "https://idp.example.com"
        assert settings["idp"]["singleSignOnService"]["url"] == "https://idp.example.com/sso"
        assert settings["sp"]["entityId"] == "https://rtube.example.com"
        assert settings["sp"]["assertionConsumerService"]["url"] == "https://rtube.example.com/auth/saml/acs"

    def test_test_connection_success(self):
        """Test connection test with valid config."""
        config = SAMLConfig(
            idp_entity_id="https://idp.example.com",
            idp_sso_url="https://idp.example.com/sso",
            idp_cert="MIICcertificate",
            sp_entity_id="https://rtube.example.com",
            username_attribute="uid",
            email_attribute="email",
            name_attribute="displayName",
        )
        service = SAMLAuthService(config)

        assert service.test_connection() is True


class TestSAMLLoginRoute:
    """Tests for SAML login functionality in routes."""

    @pytest.fixture
    def saml_app(self):
        """Create app with SAML enabled (mocked)."""
        os.environ["TESTING"] = "true"

        from rtube.app import create_app

        mock_saml_service = Mock()
        mock_saml_service.get_login_url = Mock(
            return_value="https://idp.example.com/sso?SAMLRequest=..."
        )
        mock_saml_service.get_metadata = Mock(
            return_value='<?xml version="1.0"?><EntityDescriptor/>'
        )

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }

        app = create_app(test_config=test_config)

        app.config["SAML_ENABLED"] = True
        app.config["SAML_SERVICE"] = mock_saml_service

        yield app, mock_saml_service

        with app.app_context():
            db.session.remove()

    def test_saml_login_redirects_to_idp(self, saml_app):
        """Test that SAML login redirects to the IdP."""
        app, mock_saml_service = saml_app

        client = app.test_client()

        response = client.get('/auth/saml/login')

        assert response.status_code == 302
        assert 'idp.example.com' in response.location

    def test_saml_metadata_endpoint(self, saml_app):
        """Test SAML SP metadata endpoint."""
        app, mock_saml_service = saml_app

        client = app.test_client()

        response = client.get('/auth/saml/metadata')

        assert response.status_code == 200
        assert 'application/xml' in response.content_type
        assert b'EntityDescriptor' in response.data

    def test_login_page_shows_saml_button(self, saml_app):
        """Test that login page shows SAML button when enabled."""
        app, mock_saml_service = saml_app

        client = app.test_client()

        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Sign in with SSO (SAML)' in response.data


class TestSAMLUserCreation:
    """Tests for SAML user auto-creation."""

    @pytest.fixture
    def saml_app_with_acs(self):
        """Create app with SAML enabled and mocked ACS."""
        os.environ["TESTING"] = "true"

        from rtube.app import create_app

        mock_saml_service = Mock()
        mock_saml_service.get_login_url = Mock(
            return_value="https://idp.example.com/sso"
        )
        mock_saml_service.process_response = Mock(return_value={
            'name_id': 'saml-user-67890',
            'username': 'samluser',
            'email': 'samluser@example.com',
            'name': 'SAML User',
            'attributes': {},
            'session_index': 'session-123',
        })

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }

        app = create_app(test_config=test_config)

        app.config["SAML_ENABLED"] = True
        app.config["SAML_SERVICE"] = mock_saml_service

        yield app, mock_saml_service

        with app.app_context():
            db.session.remove()

    def test_saml_acs_creates_user(self, saml_app_with_acs):
        """Test that SAML ACS auto-creates user on first login."""
        app, mock_saml_service = saml_app_with_acs

        client = app.test_client()

        # POST to ACS with mock SAML response
        response = client.post('/auth/saml/acs', data={
            'SAMLResponse': 'base64encodedresponse',
        })

        assert response.status_code == 302

        # Verify user was created
        with app.app_context():
            user = User.query.filter_by(sso_subject='saml-user-67890').first()
            assert user is not None
            assert user.auth_type == 'saml'
            assert user.username == 'samluser'

    def test_saml_acs_existing_user(self, saml_app_with_acs):
        """Test SAML ACS with existing SAML user."""
        app, mock_saml_service = saml_app_with_acs

        # Create existing user
        with app.app_context():
            user = User(
                username='samluser',
                auth_type='saml',
                sso_subject='saml-user-67890'
            )
            db.session.add(user)
            db.session.commit()

        client = app.test_client()

        response = client.post('/auth/saml/acs', data={
            'SAMLResponse': 'base64encodedresponse',
        })

        assert response.status_code == 302

        # Verify no duplicate user created
        with app.app_context():
            users = User.query.filter_by(sso_subject='saml-user-67890').all()
            assert len(users) == 1

    def test_saml_acs_with_relay_state(self, saml_app_with_acs):
        """Test SAML ACS redirects to RelayState."""
        app, mock_saml_service = saml_app_with_acs

        client = app.test_client()

        response = client.post('/auth/saml/acs', data={
            'SAMLResponse': 'base64encodedresponse',
            'RelayState': 'http://localhost/videos/123',
        })

        assert response.status_code == 302
        assert response.location == 'http://localhost/videos/123'

    def test_saml_acs_validation_error(self, saml_app_with_acs):
        """Test SAML ACS with validation error."""
        app, mock_saml_service = saml_app_with_acs

        mock_saml_service.process_response.side_effect = ValueError("Invalid signature")

        client = app.test_client()

        response = client.post('/auth/saml/acs', data={
            'SAMLResponse': 'invalid-response',
        })

        assert response.status_code == 302
        assert '/auth/login' in response.location


class TestUserModelSAML:
    """Tests for User model SAML-related methods."""

    def test_is_saml_user(self, app):
        """Test is_saml_user method."""
        with app.app_context():
            saml_user = User(username='samltest', auth_type='saml', sso_subject='nameid-123')
            local_user = User(username='localtest', auth_type='local')

            assert saml_user.is_saml_user() is True
            assert saml_user.is_sso_user() is True
            assert saml_user.is_local_user() is False

            assert local_user.is_saml_user() is False
            assert local_user.is_sso_user() is False
            assert local_user.is_local_user() is True

    def test_saml_user_check_password_fails(self, app):
        """Test that check_password returns False for SAML users."""
        with app.app_context():
            saml_user = User(username='samltest', auth_type='saml', sso_subject='nameid-123')

            # SAML users should not be able to use local password check
            assert saml_user.check_password('anypassword') is False


class TestSSODisabled:
    """Tests to ensure SSO routes work correctly when disabled."""

    def test_oidc_login_disabled(self, client):
        """Test OIDC login redirects when not configured."""
        response = client.get('/auth/oidc/login', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_saml_login_disabled(self, client):
        """Test SAML login redirects when not configured."""
        response = client.get('/auth/saml/login', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_saml_metadata_disabled(self, client):
        """Test SAML metadata returns 404 when not configured."""
        response = client.get('/auth/saml/metadata')
        assert response.status_code == 404

    def test_login_page_no_sso_buttons(self, client):
        """Test that login page doesn't show SSO buttons when disabled."""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Sign in with SSO (OIDC)' not in response.data
        assert b'Sign in with SSO (SAML)' not in response.data
