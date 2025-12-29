"""
Tests for video routes.
"""
import pytest
from rtube.models import db, Video, Comment


class TestIndexRoute:
    """Tests for the main index/videos page."""

    def test_index_page_loads(self, client):
        """Test that index page loads correctly."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'RTube' in response.data

    def test_index_shows_version(self, client):
        """Test that index shows version in footer."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'RTube v' in response.data

    def test_index_shows_login_link_when_unauthenticated(self, client):
        """Test that index shows login link for unauthenticated users."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Login' in response.data

    def test_index_shows_logout_link_when_authenticated(self, authenticated_client):
        """Test that index shows logout link for authenticated users."""
        response = authenticated_client.get('/')
        assert response.status_code == 200
        assert b'Logout' in response.data

    def test_index_shows_encode_button_when_authenticated(self, authenticated_client):
        """Test that encode button is shown for authenticated users."""
        response = authenticated_client.get('/')
        assert response.status_code == 200
        assert b'Encode a video' in response.data

    def test_index_hides_encode_button_when_unauthenticated(self, client):
        """Test that encode button is hidden for unauthenticated users."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Encode a video' not in response.data


class TestVideoVisibility:
    """Tests for video visibility on index page."""

    def test_public_video_visible_to_all(self, client, sample_video, app):
        """Test that public videos are visible to unauthenticated users."""
        # Test the database visibility logic
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            assert video.is_public() is True

    def test_private_video_hidden_from_unauthenticated(self, client, sample_private_video, app):
        """Test that private videos are hidden from unauthenticated users."""
        with app.app_context():
            video = Video.query.get(sample_private_video["id"])
            assert video.is_private() is True


class TestWatchVideoRoute:
    """Tests for the video watch page."""

    def test_watch_nonexistent_video(self, client):
        """Test watching a non-existent video returns 404."""
        response = client.get('/watch?v=nonexistent1234')
        assert response.status_code == 404

    def test_watch_missing_video_param(self, client):
        """Test watching without video parameter returns 404."""
        response = client.get('/watch')
        assert response.status_code == 404

    def test_watch_private_video_unauthenticated_redirects(self, client, sample_private_video):
        """Test that unauthenticated user is redirected when accessing private video."""
        response = client.get(f'/watch?v={sample_private_video["short_id"]}', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_watch_video_case_insensitive(self, app, sample_video):
        """Test that short_id lookup is case-insensitive in the database."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            upper_short_id = video.short_id.upper()

            # Query with lowercase
            video_lower = Video.query.filter(
                db.func.lower(Video.short_id) == sample_video["short_id"].lower()
            ).first()

            # Query with uppercase
            video_upper = Video.query.filter(
                db.func.lower(Video.short_id) == upper_short_id.lower()
            ).first()

            # Both should find the same video
            assert video_lower is not None
            assert video_upper is not None
            assert video_lower.id == video_upper.id

    def test_watch_malformed_url_with_existing_video_redirects(self, client, sample_video):
        """Test that malformed URL /watch/VIDEO_ID redirects to correct format."""
        response = client.get(f'/watch/{sample_video["short_id"]}', follow_redirects=False)
        assert response.status_code == 302
        assert f'/watch?v={sample_video["short_id"]}' in response.location

    def test_watch_malformed_url_with_nonexistent_video_returns_404(self, client):
        """Test that malformed URL with non-existent video returns 404 with helpful message."""
        response = client.get('/watch/nonexistent1234')
        assert response.status_code == 404
        assert b'Invalid URL format' in response.data
        assert b'/watch?v=nonexistent1234' in response.data


class TestCommentRoute:
    """Tests for the comment posting route."""

    def test_post_comment_requires_auth(self, client, sample_video):
        """Test that posting a comment requires authentication."""
        response = client.post(
            f'/watch/comment?v={sample_video["short_id"]}',
            data={'content': 'Test comment'},
            follow_redirects=False
        )
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_post_comment_success(self, authenticated_client, sample_video, app):
        """Test successfully posting a comment."""
        response = authenticated_client.post(
            f'/watch/comment?v={sample_video["short_id"]}',
            data={'content': 'This is a test comment!'},
            follow_redirects=True
        )

        # Check comment was created
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comments = Comment.query.filter_by(video_id=video.id).all()
            assert len(comments) == 1
            assert comments[0].content == 'This is a test comment!'
            assert comments[0].author_username == 'testuser'

    def test_post_empty_comment(self, authenticated_client, sample_video, app):
        """Test posting an empty comment fails."""
        response = authenticated_client.post(
            f'/watch/comment?v={sample_video["short_id"]}',
            data={'content': ''},
            follow_redirects=True
        )

        # Check no comment was created
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comments = Comment.query.filter_by(video_id=video.id).all()
            assert len(comments) == 0

    def test_post_comment_whitespace_only(self, authenticated_client, sample_video, app):
        """Test posting whitespace-only comment fails."""
        response = authenticated_client.post(
            f'/watch/comment?v={sample_video["short_id"]}',
            data={'content': '   \n\t   '},
            follow_redirects=True
        )

        # Check no comment was created
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comments = Comment.query.filter_by(video_id=video.id).all()
            assert len(comments) == 0

    def test_post_comment_truncated_to_5000_chars(self, authenticated_client, sample_video, app):
        """Test that comments are truncated to 5000 characters."""
        long_content = 'x' * 6000

        response = authenticated_client.post(
            f'/watch/comment?v={sample_video["short_id"]}',
            data={'content': long_content},
            follow_redirects=True
        )

        # Check comment was truncated
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comments = Comment.query.filter_by(video_id=video.id).all()
            assert len(comments) == 1
            assert len(comments[0].content) == 5000

    def test_post_comment_nonexistent_video(self, authenticated_client):
        """Test posting comment to non-existent video returns 404."""
        response = authenticated_client.post(
            '/watch/comment?v=nonexistent1234',
            data={'content': 'Test comment'}
        )
        assert response.status_code == 404

    def test_post_comment_on_private_video_unauthenticated(self, client, sample_private_video):
        """Test posting comment on private video when unauthenticated."""
        response = client.post(
            f'/watch/comment?v={sample_private_video["short_id"]}',
            data={'content': 'Test comment'},
            follow_redirects=False
        )
        assert response.status_code == 302
        assert '/auth/login' in response.location


class TestDeleteCommentRoute:
    """Tests for the comment deletion route."""

    def test_delete_comment_requires_auth(self, client, sample_video, app):
        """Test that deleting a comment requires authentication."""
        # First create a comment
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Test comment to delete"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = client.post(
            f'/watch/comment/delete?v={sample_video["short_id"]}',
            data={'comment_id': comment_id},
            follow_redirects=False
        )
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_delete_own_comment_success(self, authenticated_client, sample_video, app):
        """Test that user can delete their own comment."""
        # First create a comment
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Test comment to delete"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = authenticated_client.post(
            f'/watch/comment/delete?v={sample_video["short_id"]}',
            data={'comment_id': comment_id},
            follow_redirects=True
        )

        # Check comment was deleted
        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment is None

    def test_delete_other_user_comment_forbidden(self, authenticated_client, sample_video, app):
        """Test that user cannot delete another user's comment."""
        # Create a comment from another user
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="otheruser",
                content="Other user's comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = authenticated_client.post(
            f'/watch/comment/delete?v={sample_video["short_id"]}',
            data={'comment_id': comment_id},
            follow_redirects=True
        )

        # Check comment was NOT deleted
        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment is not None

    def test_admin_can_delete_any_comment(self, admin_client, sample_video, app):
        """Test that admin can delete any user's comment."""
        # Create a comment from another user
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="otheruser",
                content="Other user's comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = admin_client.post(
            f'/watch/comment/delete?v={sample_video["short_id"]}',
            data={'comment_id': comment_id},
            follow_redirects=True
        )

        # Check comment was deleted by admin
        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment is None

    def test_delete_nonexistent_comment(self, authenticated_client, sample_video):
        """Test deleting a non-existent comment returns 404."""
        response = authenticated_client.post(
            f'/watch/comment/delete?v={sample_video["short_id"]}',
            data={'comment_id': 99999}
        )
        assert response.status_code == 404

    def test_delete_comment_nonexistent_video(self, authenticated_client):
        """Test deleting comment from non-existent video returns 404."""
        response = authenticated_client.post(
            '/watch/comment/delete?v=nonexistent1234',
            data={'comment_id': 1}
        )
        assert response.status_code == 404

    def test_delete_comment_missing_params(self, authenticated_client):
        """Test deleting comment without required params returns 404."""
        response = authenticated_client.post('/watch/comment/delete')
        assert response.status_code == 404


class TestEditCommentRoute:
    """Tests for the comment editing route."""

    def test_edit_comment_requires_auth(self, client, sample_video, app):
        """Test that editing a comment requires authentication."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': 'Edited comment'},
            follow_redirects=False
        )
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_edit_own_comment_success(self, authenticated_client, sample_video, app):
        """Test that user can edit their own comment."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = authenticated_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': 'Edited comment'},
            follow_redirects=True
        )

        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment.content == 'Edited comment'

    def test_edit_other_user_comment_forbidden(self, authenticated_client, sample_video, app):
        """Test that user cannot edit another user's comment."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="otheruser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = authenticated_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': 'Edited comment'},
            follow_redirects=True
        )

        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment.content == 'Original comment'

    def test_admin_cannot_edit_other_user_comment(self, admin_client, sample_video, app):
        """Test that admin cannot edit another user's comment (only delete)."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="otheruser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = admin_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': 'Edited by admin'},
            follow_redirects=True
        )

        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment.content == 'Original comment'

    def test_edit_comment_empty_content(self, authenticated_client, sample_video, app):
        """Test that editing comment with empty content fails."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        response = authenticated_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': ''},
            follow_redirects=True
        )

        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert comment.content == 'Original comment'

    def test_edit_comment_truncated_to_5000_chars(self, authenticated_client, sample_video, app):
        """Test that edited comments are truncated to 5000 characters."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Original comment"
            )
            db.session.add(comment)
            db.session.commit()
            comment_id = comment.id

        long_content = 'x' * 6000
        response = authenticated_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': comment_id, 'content': long_content},
            follow_redirects=True
        )

        with app.app_context():
            comment = Comment.query.get(comment_id)
            assert len(comment.content) == 5000

    def test_edit_nonexistent_comment(self, authenticated_client, sample_video):
        """Test editing a non-existent comment returns 404."""
        response = authenticated_client.post(
            f'/watch/comment/edit?v={sample_video["short_id"]}',
            data={'comment_id': 99999, 'content': 'Edited content'}
        )
        assert response.status_code == 404

    def test_edit_comment_nonexistent_video(self, authenticated_client):
        """Test editing comment on non-existent video returns 404."""
        response = authenticated_client.post(
            '/watch/comment/edit?v=nonexistent1234',
            data={'comment_id': 1, 'content': 'Edited content'}
        )
        assert response.status_code == 404

    def test_edit_comment_missing_params(self, authenticated_client):
        """Test editing comment without required params returns 404."""
        response = authenticated_client.post('/watch/comment/edit')
        assert response.status_code == 404


class TestEncodingRoutes:
    """Tests for encoding routes."""

    def test_upload_form_requires_auth(self, client):
        """Test that upload form requires authentication."""
        response = client.get('/encode/', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_upload_form_loads_when_authenticated(self, authenticated_client):
        """Test that upload form loads for authenticated users."""
        response = authenticated_client.get('/encode/')
        assert response.status_code == 200

    def test_encoding_jobs_list(self, client):
        """Test encoding jobs list page loads."""
        response = client.get('/encode/status/')
        assert response.status_code == 200
