"""
Tests for LDAP authentication.
"""
import os
from unittest.mock import Mock, patch

import pytest

from rtube.models import db
from rtube.models_auth import User, UserRole
from rtube.services.ldap_auth import LDAPAuthService, LDAPConfig


class TestLDAPConfig:
    """Tests for LDAP configuration."""

    def test_from_env_disabled(self):
        """Test that LDAP is disabled by default."""
        config = LDAPConfig.from_env({})
        assert config is None

    def test_from_env_enabled(self):
        """Test LDAP configuration from environment variables."""
        env = {
            "RTUBE_LDAP_ENABLED": "true",
            "RTUBE_LDAP_SERVER": "ldap://ldap.example.com:389",
            "RTUBE_LDAP_USE_SSL": "false",
            "RTUBE_LDAP_BIND_DN": "cn=readonly,dc=example,dc=com",
            "RTUBE_LDAP_BIND_PASSWORD": "secret",
            "RTUBE_LDAP_USER_BASE": "ou=users,dc=example,dc=com",
            "RTUBE_LDAP_USER_FILTER": "(uid={username})",
            "RTUBE_LDAP_USERNAME_ATTRIBUTE": "uid",
        }
        config = LDAPConfig.from_env(env)

        assert config is not None
        assert config.server == "ldap://ldap.example.com:389"
        assert config.use_ssl is False
        assert config.bind_dn == "cn=readonly,dc=example,dc=com"
        assert config.bind_password == "secret"
        assert config.user_base == "ou=users,dc=example,dc=com"
        assert config.user_filter == "(uid={username})"
        assert config.username_attribute == "uid"

    def test_from_env_defaults(self):
        """Test LDAP configuration with minimal environment variables."""
        env = {"RTUBE_LDAP_ENABLED": "true"}
        config = LDAPConfig.from_env(env)

        assert config is not None
        assert config.server == "ldap://localhost:389"
        assert config.user_filter == "(uid={username})"
        assert config.username_attribute == "uid"


class TestLDAPAuthService:
    """Tests for LDAP authentication service."""

    def test_authenticate_empty_credentials(self):
        """Test that empty credentials fail authentication."""
        config = LDAPConfig(
            server="ldap://localhost:389",
            use_ssl=False,
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
            user_base="ou=users,dc=example,dc=com",
            user_filter="(uid={username})",
            username_attribute="uid",
        )
        service = LDAPAuthService(config)

        assert service.authenticate("", "password") is False
        assert service.authenticate("user", "") is False
        assert service.authenticate("", "") is False

    @patch("rtube.services.ldap_auth.Connection")
    @patch("rtube.services.ldap_auth.Server")
    def test_authenticate_success(self, mock_server_class, mock_conn_class):
        """Test successful LDAP authentication."""
        config = LDAPConfig(
            server="ldap://localhost:389",
            use_ssl=False,
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
            user_base="ou=users,dc=example,dc=com",
            user_filter="(uid={username})",
            username_attribute="uid",
        )
        service = LDAPAuthService(config)

        # Mock the bind connection for user search
        mock_bind_conn = Mock()
        mock_entry = Mock()
        mock_entry.entry_dn = "uid=testuser,ou=users,dc=example,dc=com"
        mock_bind_conn.entries = [mock_entry]
        mock_bind_conn.search = Mock()

        # Mock the user authentication connection
        mock_auth_conn = Mock()

        # First call is bind connection (for search), second is user auth
        mock_conn_class.side_effect = [mock_bind_conn, mock_auth_conn]

        result = service.authenticate("testuser", "password123")

        assert result is True
        mock_auth_conn.unbind.assert_called_once()

    @patch("rtube.services.ldap_auth.Connection")
    @patch("rtube.services.ldap_auth.Server")
    def test_authenticate_user_not_found(self, mock_server_class, mock_conn_class):
        """Test LDAP authentication when user is not found."""
        config = LDAPConfig(
            server="ldap://localhost:389",
            use_ssl=False,
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
            user_base="ou=users,dc=example,dc=com",
            user_filter="(uid={username})",
            username_attribute="uid",
        )
        service = LDAPAuthService(config)

        # Mock empty search results
        mock_bind_conn = Mock()
        mock_bind_conn.entries = []
        mock_bind_conn.search = Mock()
        mock_conn_class.return_value = mock_bind_conn

        result = service.authenticate("nonexistent", "password123")

        assert result is False


class TestLDAPLoginRoute:
    """Tests for LDAP login functionality in routes."""

    @pytest.fixture
    def ldap_app(self):
        """Create app with LDAP enabled (mocked)."""
        # Set testing environment
        os.environ["TESTING"] = "true"

        from rtube.app import create_app

        # Create a mock LDAP service
        mock_ldap_service = Mock()
        mock_ldap_service.authenticate = Mock(return_value=False)

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }

        app = create_app(test_config=test_config)

        # Set LDAP config after app creation to override
        app.config["LDAP_ENABLED"] = True
        app.config["LDAP_SERVICE"] = mock_ldap_service

        yield app, mock_ldap_service

        with app.app_context():
            db.session.remove()

    def test_ldap_login_success_creates_user(self, ldap_app):
        """Test that LDAP login auto-creates user on first login."""
        app, mock_ldap_service = ldap_app
        mock_ldap_service.authenticate.return_value = True

        client = app.test_client()

        response = client.post('/auth/login', data={
            'username': 'ldapuser',
            'password': 'ldappassword'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify user was created
        with app.app_context():
            user = User.query.filter_by(username='ldapuser').first()
            assert user is not None
            assert user.auth_type == 'ldap'
            assert user.password_hash is None

    def test_ldap_login_existing_user(self, ldap_app):
        """Test LDAP login with existing LDAP user."""
        app, mock_ldap_service = ldap_app
        mock_ldap_service.authenticate.return_value = True

        # Create existing LDAP user
        with app.app_context():
            user = User(username='existingldap', auth_type='ldap')
            db.session.add(user)
            db.session.commit()

        client = app.test_client()

        response = client.post('/auth/login', data={
            'username': 'existingldap',
            'password': 'ldappassword'
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_ldap_login_failure(self, ldap_app):
        """Test LDAP login with invalid credentials."""
        app, mock_ldap_service = ldap_app
        mock_ldap_service.authenticate.return_value = False

        client = app.test_client()

        response = client.post('/auth/login', data={
            'username': 'baduser',
            'password': 'badpassword'
        })

        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_local_admin_login_in_ldap_mode(self, ldap_app):
        """Test that local admin can still login when LDAP is enabled."""
        app, mock_ldap_service = ldap_app

        # Create local admin user
        with app.app_context():
            admin = User(
                username='admin',
                role=UserRole.ADMIN.value,
                auth_type='local'
            )
            admin.set_password('AdminPassword123!')
            db.session.add(admin)
            db.session.commit()

        client = app.test_client()

        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

        assert response.status_code == 200
        # LDAP authenticate should NOT be called for admin
        mock_ldap_service.authenticate.assert_not_called()

    def test_registration_disabled_in_ldap_mode(self, ldap_app):
        """Test that registration is disabled when LDAP is enabled."""
        app, mock_ldap_service = ldap_app

        client = app.test_client()

        # GET request should redirect
        response = client.get('/auth/register', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

        # POST request should also redirect
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'password': 'NewPassword123!',
            'password_confirm': 'NewPassword123!'
        }, follow_redirects=False)
        assert response.status_code == 302

    def test_login_page_shows_ldap_message(self, ldap_app):
        """Test that login page shows LDAP info message."""
        app, mock_ldap_service = ldap_app

        client = app.test_client()

        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'LDAP credentials' in response.data

    def test_login_page_hides_register_link(self, ldap_app):
        """Test that login page hides register link in LDAP mode."""
        app, mock_ldap_service = ldap_app

        client = app.test_client()

        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Register' not in response.data


class TestLocalAuthStillWorks:
    """Tests to ensure local auth still works when LDAP is disabled."""

    def test_local_login_works(self, client, sample_user):
        """Test that local login still works without LDAP."""
        response = client.post('/auth/login', data={
            'username': sample_user['username'],
            'password': sample_user['password']
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Logout' in response.data

    def test_registration_works(self, client):
        """Test that registration works without LDAP."""
        response = client.get('/auth/register')
        assert response.status_code == 200
        assert b'Register' in response.data

    def test_login_page_shows_register_link(self, client):
        """Test that login page shows register link without LDAP."""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Register' in response.data


class TestUserModel:
    """Tests for User model LDAP-related methods."""

    def test_is_ldap_user(self, app):
        """Test is_ldap_user method."""
        with app.app_context():
            ldap_user = User(username='ldaptest', auth_type='ldap')
            local_user = User(username='localtest', auth_type='local')

            assert ldap_user.is_ldap_user() is True
            assert ldap_user.is_local_user() is False

            assert local_user.is_ldap_user() is False
            assert local_user.is_local_user() is True

    def test_ldap_user_check_password_fails(self, app):
        """Test that check_password returns False for LDAP users."""
        with app.app_context():
            ldap_user = User(username='ldaptest', auth_type='ldap')

            # LDAP users should not be able to use local password check
            assert ldap_user.check_password('anypassword') is False

    def test_default_auth_type_is_local(self, app):
        """Test that default auth_type is 'local' when persisted."""
        with app.app_context():
            # Create and persist user to get database default
            user = User(username='newuser')
            user.set_password('TestPassword123!')
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
            assert user.auth_type == 'local'
