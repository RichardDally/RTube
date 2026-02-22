"""
Tests for RTube database models.
"""
from rtube.models import db, Video, VideoVisibility, Comment, generate_unique_short_id
from rtube.models_auth import User, UserRole


class TestVideoModel:
    """Tests for the Video model."""

    def test_create_video(self, app):
        """Test creating a video with all fields."""
        with app.app_context():
            video = Video(
                title="Test Video",
                description="Test description",
                language="en",
                visibility="public",
                filename="test_video",
                owner_username="testuser"
            )
            db.session.add(video)
            db.session.commit()

            assert video.id is not None
            assert video.short_id is not None
            assert len(video.short_id) == 16
            assert video.title == "Test Video"
            assert video.description == "Test description"
            assert video.language == "en"
            assert video.visibility == "public"
            assert video.view_count == 0
            assert video.owner_username == "testuser"

    def test_video_short_id_generated_automatically(self, app):
        """Test that short_id is generated automatically."""
        with app.app_context():
            video = Video(title="Test", filename="test")
            db.session.add(video)
            db.session.commit()

            assert video.short_id is not None
            assert len(video.short_id) == 16
            # Check alphanumeric
            assert video.short_id.isalnum()

    def test_video_short_id_unique(self, app):
        """Test that each video gets a unique short_id."""
        with app.app_context():
            video1 = Video(title="Video 1", filename="video1")
            video2 = Video(title="Video 2", filename="video2")
            db.session.add(video1)
            db.session.add(video2)
            db.session.commit()

            assert video1.short_id != video2.short_id

    def test_video_visibility_public(self, app):
        """Test public video visibility."""
        with app.app_context():
            video = Video(
                title="Public Video",
                filename="public",
                visibility=VideoVisibility.PUBLIC.value
            )
            db.session.add(video)
            db.session.commit()

            assert video.is_public() is True
            assert video.is_private() is False

    def test_video_visibility_private(self, app):
        """Test private video visibility."""
        with app.app_context():
            video = Video(
                title="Private Video",
                filename="private",
                visibility=VideoVisibility.PRIVATE.value
            )
            db.session.add(video)
            db.session.commit()

            assert video.is_public() is False
            assert video.is_private() is True

    def test_video_default_visibility_is_public(self, app):
        """Test that default visibility is public."""
        with app.app_context():
            video = Video(title="Test", filename="test")
            db.session.add(video)
            db.session.commit()

            assert video.visibility == VideoVisibility.PUBLIC.value
            assert video.is_public() is True

    def test_increment_views(self, app):
        """Test incrementing view count."""
        with app.app_context():
            video = Video(title="Test", filename="test")
            db.session.add(video)
            db.session.commit()

            assert video.view_count == 0

            video.increment_views()
            assert video.view_count == 1

            video.increment_views()
            video.increment_views()
            assert video.view_count == 3

    def test_video_with_optional_fields_null(self, app):
        """Test video with optional fields as null."""
        with app.app_context():
            video = Video(title="Minimal Video", filename="minimal")
            db.session.add(video)
            db.session.commit()

            assert video.description is None
            assert video.language is None
            assert video.thumbnail is None
            assert video.owner_username is None


class TestGenerateUniqueShortId:
    """Tests for the short ID generation function."""

    def test_generate_short_id_length(self, app):
        """Test that generated short_id has correct length."""
        with app.app_context():
            short_id = generate_unique_short_id()
            assert len(short_id) == 16

    def test_generate_short_id_custom_length(self, app):
        """Test generating short_id with custom length."""
        with app.app_context():
            short_id = generate_unique_short_id(length=8)
            assert len(short_id) == 8

    def test_generate_short_id_alphanumeric(self, app):
        """Test that short_id contains only alphanumeric characters."""
        with app.app_context():
            for _ in range(10):
                short_id = generate_unique_short_id()
                assert short_id.isalnum()
                # Should be lowercase
                assert short_id == short_id.lower()


class TestUserModel:
    """Tests for the User model."""

    def test_create_user(self, app):
        """Test creating a user."""
        with app.app_context():
            user = User(
                username="newuser",
                role=UserRole.UPLOADER.value
            )
            user.set_password("SecurePass123!")
            db.session.add(user)
            db.session.commit()

            assert user.id is not None
            assert user.username == "newuser"
            assert user.role == UserRole.UPLOADER.value
            assert user.password_hash is not None
            assert user.password_hash != "SecurePass123!"  # Password should be hashed

    def test_password_hashing(self, app):
        """Test password is properly hashed."""
        with app.app_context():
            user = User(username="hashtest")
            user.set_password("MyPassword123!")

            # Password hash should start with argon2 identifier
            assert user.password_hash.startswith("$argon2")

    def test_password_verification_correct(self, app):
        """Test correct password verification."""
        with app.app_context():
            user = User(username="verifytest")
            user.set_password("CorrectPassword123!")

            assert user.check_password("CorrectPassword123!") is True

    def test_password_verification_incorrect(self, app):
        """Test incorrect password verification."""
        with app.app_context():
            user = User(username="verifytest")
            user.set_password("CorrectPassword123!")

            assert user.check_password("WrongPassword123!") is False

    def test_user_roles(self, app):
        """Test user role methods."""
        with app.app_context():
            uploader = User(username="uploader", role=UserRole.UPLOADER.value)
            admin = User(username="admin", role=UserRole.ADMIN.value)

            assert uploader.is_admin() is False
            assert uploader.is_uploader() is True

            assert admin.is_admin() is True
            assert admin.is_uploader() is True  # Admins can also upload

    def test_default_role_is_viewer(self, app):
        """Test that default role is viewer."""
        with app.app_context():
            user = User(username="defaultrole")
            user.set_password("Test123!")
            db.session.add(user)
            db.session.commit()

            assert user.role == UserRole.VIEWER.value


class TestPasswordValidation:
    """Tests for password validation."""

    def test_valid_password(self):
        """Test a valid password passes validation."""
        is_valid, errors = User.validate_password("MySecureP@ss99!")
        assert is_valid is True
        assert len(errors) == 0

    def test_password_too_short(self):
        """Test password under 12 characters fails."""
        is_valid, errors = User.validate_password("Short1!")
        assert is_valid is False
        assert any("12 characters" in e for e in errors)

    def test_password_missing_uppercase(self):
        """Test password without uppercase fails."""
        is_valid, errors = User.validate_password("nouppercase123!")
        assert is_valid is False
        assert any("uppercase" in e for e in errors)

    def test_password_missing_lowercase(self):
        """Test password without lowercase fails."""
        is_valid, errors = User.validate_password("NOLOWERCASE123!")
        assert is_valid is False
        assert any("lowercase" in e for e in errors)

    def test_password_missing_digit(self):
        """Test password without digit fails."""
        is_valid, errors = User.validate_password("NoDigitsHere!!!")
        assert is_valid is False
        assert any("digit" in e for e in errors)

    def test_password_missing_special_char(self):
        """Test password without special character fails."""
        is_valid, errors = User.validate_password("NoSpecialChar123")
        assert is_valid is False
        assert any("special character" in e for e in errors)

    def test_password_common_pattern(self):
        """Test password with common pattern fails."""
        is_valid, errors = User.validate_password("Password123!!")
        assert is_valid is False
        assert any("common pattern" in e for e in errors)

    def test_password_sequential_chars(self):
        """Test password with sequential characters fails."""
        is_valid, errors = User.validate_password("Myabcd12345!!")
        assert is_valid is False
        assert any("sequential" in e for e in errors)

    def test_password_repeated_chars(self):
        """Test password with repeated characters fails."""
        is_valid, errors = User.validate_password("Aaaaaa123456!")
        assert is_valid is False
        assert any("common pattern" in e for e in errors)


class TestUsernameValidation:
    """Tests for username validation."""

    def test_valid_username(self):
        """Test a valid username passes validation."""
        is_valid, errors = User.validate_username("valid_user123")
        assert is_valid is True
        assert len(errors) == 0

    def test_username_too_short(self):
        """Test username under 3 characters fails."""
        is_valid, errors = User.validate_username("ab")
        assert is_valid is False
        assert any("at least 3" in e for e in errors)

    def test_username_too_long(self):
        """Test username over 30 characters fails."""
        is_valid, errors = User.validate_username("a" * 31)
        assert is_valid is False
        assert any("at most 30" in e for e in errors)

    def test_username_invalid_chars(self):
        """Test username with invalid characters fails."""
        is_valid, errors = User.validate_username("invalid@user!")
        assert is_valid is False
        assert any("letters, numbers, and underscores" in e for e in errors)

    def test_username_with_spaces(self):
        """Test username with spaces fails."""
        is_valid, errors = User.validate_username("user name")
        assert is_valid is False


class TestCommentModel:
    """Tests for the Comment model."""

    def test_create_comment(self, app, sample_video):
        """Test creating a comment."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="This is a test comment."
            )
            db.session.add(comment)
            db.session.commit()

            assert comment.id is not None
            assert comment.video_id == video.id
            assert comment.author_username == "testuser"
            assert comment.content == "This is a test comment."
            assert comment.created_at is not None

    def test_comment_video_relationship(self, app, sample_video):
        """Test comment-video relationship."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])
            comment = Comment(
                video_id=video.id,
                author_username="testuser",
                content="Test comment"
            )
            db.session.add(comment)
            db.session.commit()

            # Check relationship
            assert comment.video.id == video.id
            assert len(video.comments) == 1
            assert video.comments[0].content == "Test comment"

    def test_multiple_comments_on_video(self, app, sample_video):
        """Test multiple comments on a video."""
        with app.app_context():
            video = Video.query.get(sample_video["id"])

            for i in range(3):
                comment = Comment(
                    video_id=video.id,
                    author_username=f"user{i}",
                    content=f"Comment {i}"
                )
                db.session.add(comment)

            db.session.commit()

            video = Video.query.get(sample_video["id"])
            assert len(video.comments) == 3
