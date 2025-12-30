"""
Tests for authentication routes.
"""
import pytest
from rtube.models import db, Video, Comment
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


class TestProfileRoute:
    """Tests for the profile route."""

    def test_profile_requires_auth(self, client):
        """Test that profile page requires authentication."""
        response = client.get('/auth/profile', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_profile_accessible_when_authenticated(self, authenticated_client):
        """Test that profile page is accessible when authenticated."""
        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert b'Profile' in response.data

    def test_profile_shows_username(self, authenticated_client, sample_user):
        """Test that profile page shows the user's username."""
        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert sample_user['username'].encode() in response.data

    def test_profile_shows_user_videos(self, authenticated_client, sample_user, sample_video, app):
        """Test that profile page shows the user's videos."""
        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert b'Uploaded Videos' in response.data
        assert sample_video['title'].encode() in response.data

    def test_profile_shows_user_comments(self, authenticated_client, sample_user, sample_video, app):
        """Test that profile page shows the user's comments."""
        # Create a comment by the user
        with app.app_context():
            video = Video.query.get(sample_video['id'])
            comment = Comment(
                video_id=video.id,
                author_username=sample_user['username'],
                content="This is my test comment"
            )
            db.session.add(comment)
            db.session.commit()

        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert b'Comments' in response.data
        assert b'This is my test comment' in response.data

    def test_profile_shows_empty_message_for_no_videos(self, authenticated_client, app, sample_user):
        """Test that profile page shows message when user has no videos."""
        # Delete any videos owned by the user
        with app.app_context():
            Video.query.filter_by(owner_username=sample_user['username']).delete()
            db.session.commit()

        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert b"No videos uploaded yet" in response.data

    def test_profile_shows_empty_message_for_no_comments(self, authenticated_client, sample_user):
        """Test that profile page shows message when user has no comments."""
        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        assert b"No comments posted yet" in response.data

    def test_profile_shows_video_count(self, authenticated_client, sample_user, sample_video):
        """Test that profile page shows correct video count."""
        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        # Should show "1" in stat-value and "video" (singular) in stats section
        assert b'stat-value">1</span> video' in response.data

    def test_profile_shows_comment_count(self, authenticated_client, sample_user, sample_video, app):
        """Test that profile page shows correct comment count."""
        # Create a comment
        with app.app_context():
            video = Video.query.get(sample_video['id'])
            comment = Comment(
                video_id=video.id,
                author_username=sample_user['username'],
                content="Test comment"
            )
            db.session.add(comment)
            db.session.commit()

        response = authenticated_client.get('/auth/profile')
        assert response.status_code == 200
        # Should show "1" in stat-value and "comment" (singular) in stats section
        assert b'stat-value">1</span> comment' in response.data

    def test_profile_link_in_header(self, authenticated_client, sample_user):
        """Test that profile link is visible in the header on the main page."""
        response = authenticated_client.get('/')
        assert response.status_code == 200
        assert b'/auth/profile' in response.data


class TestUserProfileRoute:
    """Tests for viewing other users' profiles."""

    def test_user_profile_requires_auth(self, client):
        """Test that user profile page requires authentication."""
        response = client.get('/auth/profile/someuser', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_user_profile_accessible_by_any_authenticated_user(self, authenticated_client, app):
        """Test that any authenticated user can view other users' profiles."""
        # Create another user
        with app.app_context():
            other_user = User(username='otheruser')
            other_user.set_password('OtherPassword123!')
            db.session.add(other_user)
            db.session.commit()

        response = authenticated_client.get('/auth/profile/otheruser')
        assert response.status_code == 200
        assert b'otheruser' in response.data

    def test_user_profile_accessible_by_admin(self, admin_client, sample_user):
        """Test that admin can view other users' profiles."""
        response = admin_client.get(f'/auth/profile/{sample_user["username"]}')
        assert response.status_code == 200
        assert sample_user['username'].encode() in response.data

    def test_user_can_view_own_profile_via_username_route(self, authenticated_client, sample_user):
        """Test that users can view their own profile via the username route."""
        response = authenticated_client.get(f'/auth/profile/{sample_user["username"]}')
        assert response.status_code == 200
        assert sample_user['username'].encode() in response.data

    def test_user_profile_shows_videos_section(self, admin_client, sample_user, sample_video):
        """Test that admin viewing user profile sees Videos section (not My Videos)."""
        response = admin_client.get(f'/auth/profile/{sample_user["username"]}')
        assert response.status_code == 200
        assert b'Videos' in response.data
        assert sample_video['title'].encode() in response.data

    def test_user_profile_nonexistent_user(self, admin_client):
        """Test that viewing nonexistent user profile returns 404."""
        response = admin_client.get('/auth/profile/nonexistentuser')
        assert response.status_code == 404
        assert b"User not found" in response.data

    def test_admin_users_page_has_profile_links(self, admin_client, sample_user):
        """Test that admin users page has links to user profiles."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert f'/auth/profile/{sample_user["username"]}'.encode() in response.data
