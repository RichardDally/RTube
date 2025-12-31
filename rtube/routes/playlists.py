from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from rtube.models import db, Video, Playlist, PlaylistVideo

playlists_bp = Blueprint('playlists', __name__, url_prefix='/playlists')


@playlists_bp.route('/')
@login_required
def index():
    """List all playlists for the current user."""
    playlists = Playlist.query.filter_by(
        owner_username=current_user.username
    ).order_by(Playlist.updated_at.desc()).all()
    return render_template('playlists/index.html', playlists=playlists)


@playlists_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new playlist."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:255]
        description = request.form.get('description', '').strip()[:5000] or None
        video_id = request.form.get('video_id', type=int)

        if not name:
            flash("Playlist name is required.", "error")
            return redirect(request.referrer or url_for('playlists.index'))

        playlist = Playlist(
            name=name,
            description=description,
            owner_username=current_user.username
        )
        db.session.add(playlist)
        db.session.flush()

        # If a video_id was provided, add it to the playlist
        if video_id:
            video = db.session.get(Video, video_id)
            if video:
                playlist_video = PlaylistVideo(
                    playlist_id=playlist.id,
                    video_id=video_id,
                    position=0
                )
                db.session.add(playlist_video)

        db.session.commit()
        flash(f"Playlist '{name}' created successfully.", "success")

        # Redirect back to video if we came from there
        short_id = request.form.get('video_short_id')
        if short_id:
            return redirect(url_for('videos.watch_video', v=short_id))

        return redirect(url_for('playlists.view', playlist_id=playlist.id))

    return render_template('playlists/create.html')


@playlists_bp.route('/<int:playlist_id>')
@login_required
def view(playlist_id):
    """View a playlist."""
    playlist = Playlist.query.get_or_404(playlist_id)
    is_owner = playlist.owner_username == current_user.username
    can_delete = is_owner or current_user.is_admin()

    return render_template('playlists/view.html', playlist=playlist, is_owner=is_owner, can_delete=can_delete)


@playlists_bp.route('/<int:playlist_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(playlist_id):
    """Edit a playlist."""
    playlist = Playlist.query.get_or_404(playlist_id)

    if playlist.owner_username != current_user.username:
        flash("You don't have permission to edit this playlist.", "error")
        return redirect(url_for('playlists.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:255]
        description = request.form.get('description', '').strip()[:5000] or None

        if not name:
            flash("Playlist name is required.", "error")
            return redirect(url_for('playlists.edit', playlist_id=playlist_id))

        playlist.name = name
        playlist.description = description
        db.session.commit()

        flash("Playlist updated successfully.", "success")
        return redirect(url_for('playlists.view', playlist_id=playlist_id))

    return render_template('playlists/edit.html', playlist=playlist)


@playlists_bp.route('/<int:playlist_id>/delete', methods=['POST'])
@login_required
def delete(playlist_id):
    """Delete a playlist (owner or admin only)."""
    playlist = Playlist.query.get_or_404(playlist_id)

    is_owner = playlist.owner_username == current_user.username
    if not is_owner and not current_user.is_admin():
        flash("You don't have permission to delete this playlist.", "error")
        return redirect(url_for('playlists.index'))

    playlist_name = playlist.name
    db.session.delete(playlist)
    db.session.commit()

    flash(f"Playlist '{playlist_name}' deleted.", "success")
    return redirect(url_for('playlists.index'))


@playlists_bp.route('/add-video', methods=['POST'])
@login_required
def add_video():
    """Add a video to an existing playlist."""
    playlist_id = request.form.get('playlist_id', type=int)
    video_id = request.form.get('video_id', type=int)
    video_short_id = request.form.get('video_short_id', '')

    if not playlist_id or not video_id:
        flash("Invalid request.", "error")
        return redirect(request.referrer or url_for('videos.index'))

    playlist = Playlist.query.get_or_404(playlist_id)

    if playlist.owner_username != current_user.username:
        flash("You don't have permission to modify this playlist.", "error")
        return redirect(request.referrer or url_for('videos.index'))

    # Check if video is already in playlist
    existing = PlaylistVideo.query.filter_by(
        playlist_id=playlist_id,
        video_id=video_id
    ).first()

    if existing:
        flash("Video is already in this playlist.", "info")
    else:
        # Get the next position
        max_position = db.session.query(db.func.max(PlaylistVideo.position)).filter_by(
            playlist_id=playlist_id
        ).scalar() or -1

        playlist_video = PlaylistVideo(
            playlist_id=playlist_id,
            video_id=video_id,
            position=max_position + 1
        )
        db.session.add(playlist_video)
        db.session.commit()
        flash(f"Video added to '{playlist.name}'.", "success")

    if video_short_id:
        return redirect(url_for('videos.watch_video', v=video_short_id))
    return redirect(request.referrer or url_for('playlists.view', playlist_id=playlist_id))


@playlists_bp.route('/<int:playlist_id>/remove-video', methods=['POST'])
@login_required
def remove_video(playlist_id):
    """Remove a video from a playlist."""
    playlist = Playlist.query.get_or_404(playlist_id)
    video_id = request.form.get('video_id', type=int)

    if playlist.owner_username != current_user.username:
        flash("You don't have permission to modify this playlist.", "error")
        return redirect(url_for('playlists.index'))

    playlist_video = PlaylistVideo.query.filter_by(
        playlist_id=playlist_id,
        video_id=video_id
    ).first()

    if playlist_video:
        db.session.delete(playlist_video)
        db.session.commit()
        flash("Video removed from playlist.", "success")

    return redirect(url_for('playlists.view', playlist_id=playlist_id))


@playlists_bp.route('/modal-content')
@login_required
def modal_content():
    """Return the playlist modal content for AJAX loading."""
    video_id = request.args.get('video_id', type=int)
    video_short_id = request.args.get('video_short_id', '')

    playlists = Playlist.query.filter_by(
        owner_username=current_user.username
    ).order_by(Playlist.name).all()

    # Get which playlists already contain this video
    video_playlist_ids = set()
    if video_id:
        entries = PlaylistVideo.query.filter_by(video_id=video_id).all()
        video_playlist_ids = {e.playlist_id for e in entries}

    return render_template(
        'playlists/modal_content.html',
        playlists=playlists,
        video_id=video_id,
        video_short_id=video_short_id,
        video_playlist_ids=video_playlist_ids
    )
