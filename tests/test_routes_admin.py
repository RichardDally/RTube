"""Tests for admin routes."""
from datetime import datetime, timedelta

from rtube.models import db, Video, Comment
from rtube.models_auth import User, UserRole


class TestAdminUsersRoute:
    """Tests for the admin users page."""

    def test_admin_users_requires_auth(self, client):
        """Test that admin page requires authentication."""
        response = client.get('/admin/users', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_admin_users_requires_admin_role(self, authenticated_client):
        """Test that admin page requires admin role."""
        response = authenticated_client.get('/admin/users')
        assert response.status_code == 403

    def test_admin_users_accessible_by_admin(self, admin_client):
        """Test that admin can access the users page."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'User Management' in response.data

    def test_admin_users_shows_user_list(self, admin_client, sample_user, app):
        """Test that admin page shows list of users."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert sample_user['username'].encode() in response.data

    def test_admin_users_shows_video_count(self, admin_client, sample_user, sample_video, app):
        """Test that admin page shows correct video count per user."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        # The user should have 1 video (sample_video owned by testuser)
        assert b'testuser' in response.data

    def test_admin_users_shows_comment_count(self, admin_client, sample_user, sample_video, app):
        """Test that admin page shows correct comment count per user."""
        # Create a comment
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username=sample_user['username'],
                content="Test comment"
            )
            db.session.add(comment)
            db.session.commit()

        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'testuser' in response.data

    def test_admin_users_shows_online_status(self, admin_client, app):
        """Test that admin page shows user online status."""
        # The admin user should be online since they just made a request
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'Online' in response.data

    def test_admin_users_shows_offline_status(self, admin_client, sample_user, app):
        """Test that admin page shows offline status for inactive users."""
        # Set the sample user's last_seen to more than 5 minutes ago
        with app.app_context():
            user = User.query.filter_by(username=sample_user['username']).first()
            user.last_seen = datetime.utcnow() - timedelta(minutes=10)
            db.session.commit()

        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'Offline' in response.data

    def test_admin_users_shows_roles(self, admin_client, sample_user, app):
        """Test that admin page shows user roles."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'admin' in response.data
        assert b'uploader' in response.data

    def test_admin_users_shows_created_date(self, admin_client, sample_user, app):
        """Test that admin page shows user creation date."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        # Check for date format YYYY-MM-DD
        today = datetime.utcnow().strftime('%Y-%m-%d')
        assert today.encode() in response.data


class TestUserOnlineStatus:
    """Tests for user online status tracking."""

    def test_is_online_returns_true_for_recent_activity(self, app):
        """Test that is_online returns True for recent activity."""
        with app.app_context():
            user = User(username="onlineuser", role=UserRole.UPLOADER.value)
            user.set_password("TestPassword123!")
            user.last_seen = datetime.utcnow()
            db.session.add(user)
            db.session.commit()

            assert user.is_online() is True

    def test_is_online_returns_false_for_old_activity(self, app):
        """Test that is_online returns False for old activity."""
        with app.app_context():
            user = User(username="offlineuser", role=UserRole.UPLOADER.value)
            user.set_password("TestPassword123!")
            user.last_seen = datetime.utcnow() - timedelta(minutes=10)
            db.session.add(user)
            db.session.commit()

            assert user.is_online() is False

    def test_is_online_returns_false_when_never_seen(self, app):
        """Test that is_online returns False when user has never been seen."""
        with app.app_context():
            user = User(username="neverseenuser", role=UserRole.UPLOADER.value)
            user.set_password("TestPassword123!")
            user.last_seen = None
            db.session.add(user)
            db.session.commit()

            assert user.is_online() is False

    def test_is_online_custom_timeout(self, app):
        """Test that is_online respects custom timeout."""
        with app.app_context():
            user = User(username="customtimeoutuser", role=UserRole.UPLOADER.value)
            user.set_password("TestPassword123!")
            user.last_seen = datetime.utcnow() - timedelta(minutes=8)
            db.session.add(user)
            db.session.commit()

            # Default 5 minutes - should be offline
            assert user.is_online() is False
            # With 10 minute timeout - should be online
            assert user.is_online(timeout_minutes=10) is True

    def test_last_seen_updated_on_request(self, authenticated_client, sample_user, app):
        """Test that last_seen is updated when user makes a request."""
        # Make a request
        authenticated_client.get('/')

        with app.app_context():
            user = User.query.filter_by(username=sample_user['username']).first()
            assert user.last_seen is not None
            # Should be recent (within last minute)
            assert datetime.utcnow() - user.last_seen < timedelta(minutes=1)


class TestAdminChangePassword:
    """Tests for the admin change password page."""

    def test_change_password_requires_auth(self, client):
        """Test that change password page requires authentication."""
        response = client.get('/admin/change-password', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_change_password_requires_admin_role(self, authenticated_client):
        """Test that change password page requires admin role."""
        response = authenticated_client.get('/admin/change-password')
        assert response.status_code == 403

    def test_change_password_accessible_by_admin(self, admin_client):
        """Test that admin can access the change password page."""
        response = admin_client.get('/admin/change-password')
        assert response.status_code == 200
        assert b'Change Password' in response.data
        assert b'Current Password' in response.data
        assert b'New Password' in response.data

    def test_change_password_shows_requirements(self, admin_client):
        """Test that change password page shows password requirements."""
        response = admin_client.get('/admin/change-password')
        assert response.status_code == 200
        assert b'Password Requirements' in response.data
        assert b'Minimum 12 characters' in response.data

    def test_change_password_wrong_current_password(self, admin_client):
        """Test that change password fails with wrong current password."""
        response = admin_client.post('/admin/change-password', data={
            'current_password': 'wrongpassword',
            'new_password': 'NewSecure123!@#',
            'confirm_password': 'NewSecure123!@#'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Current password is incorrect' in response.data

    def test_change_password_mismatched_passwords(self, admin_client, sample_admin):
        """Test that change password fails when new passwords don't match."""
        response = admin_client.post('/admin/change-password', data={
            'current_password': sample_admin['password'],
            'new_password': 'NewSecure123!@#',
            'confirm_password': 'DifferentSecure123!@#'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'New passwords do not match' in response.data

    def test_change_password_weak_password(self, admin_client, sample_admin):
        """Test that change password fails with weak password."""
        response = admin_client.post('/admin/change-password', data={
            'current_password': sample_admin['password'],
            'new_password': 'weak',
            'confirm_password': 'weak'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Password must be at least 12 characters' in response.data

    def test_change_password_no_uppercase(self, admin_client, sample_admin):
        """Test that change password fails without uppercase letter."""
        response = admin_client.post('/admin/change-password', data={
            'current_password': sample_admin['password'],
            'new_password': 'newsecure123!@#',
            'confirm_password': 'newsecure123!@#'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'uppercase letter' in response.data

    def test_change_password_success(self, admin_client, sample_admin, app):
        """Test that change password succeeds with valid data."""
        new_password = 'NewSecure123!@#'
        response = admin_client.post('/admin/change-password', data={
            'current_password': sample_admin['password'],
            'new_password': new_password,
            'confirm_password': new_password
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Password changed successfully' in response.data

        # Verify the password was actually changed
        with app.app_context():
            admin_user = User.query.filter_by(username=sample_admin['username']).first()
            assert admin_user.check_password(new_password) is True
            assert admin_user.check_password(sample_admin['password']) is False

    def test_change_password_link_on_users_page(self, admin_client):
        """Test that change password link is visible on users page."""
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert b'Change Password' in response.data
        assert b'/admin/change-password' in response.data
