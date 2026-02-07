import pytest
from rtube.models import Video, VideoView, VideoVisibility
from rtube.models_auth import User

def test_bulk_delete_video_with_views(admin_client, app):
    """Test bulk deleting a video that has associated views."""
    # Login as admin is handled by admin_client fixture

    with app.app_context():
        # Create a video
        video = Video(
            filename="test_video_for_bulk_delete",
            title="Test Video for Bulk Delete",
            visibility=VideoVisibility.PUBLIC.value,
            owner_username="admin"
        )
        # Create a user to avoid FK issues if needed, but admin exists
        
        # We need to add them to session
        from rtube.models import db
        db.session.add(video)
        # view is already associated via video=video, but let's be explicit and just use one method
        # db.session.add(view) # recursive save might handle it, but let's be safe
        db.session.commit()
        
        # Create a view for the video (only one)
        view = VideoView(video_id=video.id)
        db.session.add(view)
        db.session.commit()
        
        video_id = video.id

    # Verify the video exists
    with app.app_context():
        assert Video.query.get(video_id) is not None
        assert VideoView.query.filter_by(video_id=video_id).count() == 1

    # Perform bulk delete action
    response = admin_client.post('/admin/videos/bulk-action', data={
        'action': 'delete',
        'video_ids': [video_id]
    }, follow_redirects=True)

    # Check for success message or failure
    # Currently expected to fail with 500 if not fixed, or database error
    # But Flask test client might catch 500 and show it
    
    # If the bug is present, this might raise an IntegrityError or returning 500
    assert response.status_code == 200
    assert b'Successfully deleted 1 video(s)' in response.data

    # Verify video is deleted
    with app.app_context():
        assert Video.query.get(video_id) is None
        assert VideoView.query.filter_by(video_id=video_id).count() == 0
