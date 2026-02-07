
import pytest
from rtube.models import Video, VideoView, VideoVisibility
from rtube.models_auth import User

def test_delete_video_with_views_from_watch_page(authenticated_client, sample_user, app):
    """Test deleting a video from the watch page that has associated views."""
    
    with app.app_context():
        # Create a video owned by the authenticated user
        video = Video(
            filename="test_video_watch_delete",
            title="Test Video Watch Delete",
            visibility=VideoVisibility.PUBLIC.value,
            owner_username=sample_user['username']
        )
        
        # We need to add them to session
        from rtube.models import db
        db.session.add(video)
        db.session.commit()
        
        # Create a view for the video
        view = VideoView(video_id=video.id)
        db.session.add(view)
        db.session.commit()
        
        video_id = video.id
        short_id = video.short_id

    # Verify the video exists
    with app.app_context():
        assert Video.query.get(video_id) is not None
        assert VideoView.query.filter_by(video_id=video_id).count() == 1

    # Perform delete action via POST request to /watch/delete
    response = authenticated_client.post(f'/watch/delete?v={short_id}', follow_redirects=True)

    # Check for success (200 OK after redirect)
    # The absence of 500 Internal Server Error confirms the fix
    assert response.status_code == 200

    # Verify video is deleted
    with app.app_context():
        assert Video.query.get(video_id) is None
        assert VideoView.query.filter_by(video_id=video_id).count() == 0
