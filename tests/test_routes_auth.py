"""
Tests for authentication routes.
"""
import pytest
from rtube.models import db
from rtube.models_auth import User, UserRole


class TestLoginRoute:
    """Tests for the login route."""

    def test_login_page_loads(self, client):
        """Test that login page loads correctly."""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Login' in response.data

    def test_login_success(self, client, sample_user):
        """Test successful login."""
        response = client.post('/auth/login', data={
            'username': sample_user['username'],
            'password': sample_user['password']
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_login_wrong_password(self, client, sample_user):
        """Test login with wrong password."""
        response = client.post('/auth/login', data={
            'username': sample_user['username'],
            'password': 'WrongPassword123!'
        })

        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'SomePassword123!'
        })

        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_empty_fields(self, client):
        """Test login with empty fields."""
        response = client.post('/auth/login', data={
            'username': '',
            'password': ''
        })

        assert response.status_code == 200
        assert b'required' in response.data.lower()


class TestRegisterRoute:
    """Tests for the registration route."""

    def test_register_page_loads(self, client):
        """Test that register page loads correctly."""
        response = client.get('/auth/register')
        assert response.status_code == 200
        assert b'Create Account' in response.data

    def test_register_success(self, client, app):
        """Test successful registration."""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'password': 'SecureP@ssword99!',
            'password_confirm': 'SecureP@ssword99!'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify user was created
        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            assert user is not None
            assert user.role == UserRole.UPLOADER.value

    def test_register_password_mismatch(self, client):
        """Test registration with mismatched passwords."""
        response = client.post('/auth/register', data={
            'username': 'newuser2',
            'password': 'SecureP@ssword99!',
            'password_confirm': 'DifferentP@ss99!'
        })

        assert response.status_code == 200
        assert b'do not match' in response.data.lower()

    def test_register_weak_password(self, client):
        """Test registration with weak password."""
        response = client.post('/auth/register', data={
            'username': 'newuser3',
            'password': 'weak',
            'password_confirm': 'weak'
        })

        assert response.status_code == 200
        # Should show password requirements error

    def test_register_duplicate_username(self, client, sample_user):
        """Test registration with existing username."""
        response = client.post('/auth/register', data={
            'username': sample_user['username'],
            'password': 'SecureP@ssword99!',
            'password_confirm': 'SecureP@ssword99!'
        })

        assert response.status_code == 200
        assert b'already taken' in response.data.lower()

    def test_register_invalid_username_too_short(self, client):
        """Test registration with username too short."""
        response = client.post('/auth/register', data={
            'username': 'ab',
            'password': 'SecureP@ssword99!',
            'password_confirm': 'SecureP@ssword99!'
        })

        assert response.status_code == 200
        assert b'at least 3' in response.data.lower()


class TestLogoutRoute:
    """Tests for the logout route."""

    def test_logout_success(self, authenticated_client):
        """Test successful logout."""
        response = authenticated_client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200

    def test_logout_unauthenticated(self, client):
        """Test logout when not authenticated redirects to login."""
        response = client.get('/auth/logout', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location


class TestAuthenticationRequired:
    """Tests for routes that require authentication."""

    def test_encode_requires_auth(self, client):
        """Test that encode page requires authentication."""
        response = client.get('/encode/', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_encode_accessible_when_authenticated(self, authenticated_client):
        """Test that encode page is accessible when authenticated."""
        response = authenticated_client.get('/encode/')
        assert response.status_code == 200
