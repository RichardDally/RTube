import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Thread

import ffmpeg_streaming
from ffmpeg_streaming import Formats, Representation, Size, Bitrate

from rtube.models import db, EncodingJob

QUALITY_PRESETS = {
    "144p": Representation(Size(256, 144), Bitrate(95 * 1024, 64 * 1024)),
    "240p": Representation(Size(426, 240), Bitrate(150 * 1024, 94 * 1024)),
    "360p": Representation(Size(640, 360), Bitrate(276 * 1024, 128 * 1024)),
    "480p": Representation(Size(854, 480), Bitrate(750 * 1024, 192 * 1024)),
    "720p": Representation(Size(1280, 720), Bitrate(2048 * 1024, 320 * 1024)),
    "1080p": Representation(Size(1920, 1080), Bitrate(4096 * 1024, 320 * 1024)),
    "1440p": Representation(Size(2560, 1440), Bitrate(6144 * 1024, 320 * 1024)),
    "2160p": Representation(Size(3840, 2160), Bitrate(17408 * 1024, 320 * 1024)),
}


class EncoderService:
    def __init__(self, app=None):
        self.app = app
        self._progress = {}

    def init_app(self, app):
        self.app = app

    def get_progress(self, job_id: int) -> dict:
        return self._progress.get(job_id, {"progress": 0, "status": "pending"})

    def encode_video(self, job_id: int, input_path: Path, output_path: Path, qualities: list[str], delete_original: bool = True, thumbnail_path: Path = None, preview_path: Path = None):
        """Lance l'encodage dans un thread séparé."""
        thread = Thread(target=self._encode_worker, args=(job_id, input_path, output_path, qualities, delete_original, thumbnail_path, preview_path))
        thread.daemon = True
        thread.start()

    def _get_video_duration(self, input_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)],
                capture_output=True,
                text=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            self.app.logger.warning(f"Failed to get video duration: {e}")
            return 0

    def _generate_thumbnail(self, input_path: Path, thumbnail_path: Path) -> bool:
        """Generate a thumbnail at a random position in the video."""
        try:
            duration = self._get_video_duration(input_path)
            if duration <= 0:
                timestamp = 1
            else:
                # Pick a random time between 10% and 90% of the video
                timestamp = random.uniform(duration * 0.1, duration * 0.9)

            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(input_path), "-vframes", "1", "-q:v", "2", str(thumbnail_path)],
                capture_output=True,
                check=True
            )
            self.app.logger.info(f"Generated thumbnail at {timestamp:.1f}s: {thumbnail_path}")
            return True
        except Exception as e:
            self.app.logger.warning(f"Failed to generate thumbnail: {e}")
            return False

    def _generate_preview(self, input_path: Path, preview_path: Path, duration: float = 4.0) -> bool:
        """Generate a short video preview (webm) for hover display.

        Creates a small, silent video clip from a representative portion of the video.

        Args:
            input_path: Path to the source video
            preview_path: Path where the preview should be saved (should end in .webm)
            duration: Duration of the preview in seconds (default 4s)

        Returns:
            True if preview was generated successfully, False otherwise
        """
        try:
            video_duration = self._get_video_duration(input_path)
            if video_duration <= 0:
                self.app.logger.warning("Cannot generate preview: video duration unknown")
                return False

            # Pick a start time between 10% and 70% of the video (leave room for duration)
            max_start = max(0, video_duration * 0.7 - duration)
            min_start = video_duration * 0.1
            if max_start <= min_start:
                start_time = min_start
            else:
                start_time = random.uniform(min_start, max_start)

            preview_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate a small, silent webm preview
            # -an: no audio
            # -vf scale: resize to 320px width, maintain aspect ratio
            # -c:v libvpx-vp9: VP9 codec for webm
            # -b:v 200k: low bitrate for small file size
            # -deadline good: balance between quality and speed
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", str(input_path),
                    "-t", str(duration),
                    "-an",  # No audio
                    "-vf", "scale=320:-2",  # 320px width, even height
                    "-c:v", "libvpx-vp9",
                    "-b:v", "200k",
                    "-deadline", "good",
                    "-cpu-used", "4",
                    str(preview_path)
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.app.logger.warning(f"ffmpeg preview error: {result.stderr}")
                return False

            if preview_path.exists() and preview_path.stat().st_size > 0:
                self.app.logger.info(f"Generated preview at {start_time:.1f}s: {preview_path}")
                return True
            else:
                self.app.logger.warning("Preview file not created or empty")
                return False

        except Exception as e:
            self.app.logger.warning(f"Failed to generate preview: {e}")
            return False

    def generate_preview_from_hls(self, videos_folder: Path, filename: str, preview_path: Path, duration: float = 4.0) -> bool:
        """Generate a preview video from an existing HLS video.

        Concatenates a few .ts segments and creates a small webm preview.

        Args:
            videos_folder: Path to the videos folder
            filename: Base filename (without extension)
            preview_path: Path where the preview should be saved (should end in .webm)
            duration: Duration of the preview in seconds (default 4s)

        Returns:
            True if preview was generated successfully, False otherwise
        """
        # Find quality-specific m3u8 files for this video - use lowest quality for preview
        quality_pattern = re.compile(rf'^{re.escape(filename)}_(\d+p)\.m3u8$')

        qualities = []
        for m3u8_file in videos_folder.glob(f'{filename}_*p.m3u8'):
            match = quality_pattern.match(m3u8_file.name)
            if match:
                quality_str = match.group(1)
                quality_num = int(quality_str.replace('p', ''))
                qualities.append((quality_num, quality_str))

        if not qualities:
            self.app.logger.warning(f"No quality variants found for {filename}")
            return False

        # Sort by resolution (ascending) and pick lowest quality for small preview
        qualities.sort(key=lambda x: x[0])
        _, lowest_quality = qualities[0]

        # Find .ts segments
        ts_pattern = f'{filename}_{lowest_quality}_*.ts'
        ts_files = sorted(videos_folder.glob(ts_pattern))

        if not ts_files:
            self.app.logger.warning(f"No .ts segments found matching {ts_pattern}")
            return False

        self.app.logger.info(f"Found {len(ts_files)} segments for {filename} at {lowest_quality}")

        # Pick segments from middle of video (between 10% and 50%)
        num_segments = len(ts_files)
        if num_segments > 4:
            start_idx = max(0, int(num_segments * 0.1))
            # Take 2-3 segments which should give us enough for 4 seconds
            end_idx = min(num_segments - 1, start_idx + 3)
        else:
            start_idx = 0
            end_idx = min(num_segments - 1, 2)

        selected_segments = ts_files[start_idx:end_idx + 1]

        try:
            preview_path.parent.mkdir(parents=True, exist_ok=True)

            # Create a concat file for ffmpeg
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                concat_file = Path(f.name)
                for ts_file in selected_segments:
                    f.write(f"file '{ts_file}'\n")

            # Generate preview from concatenated segments
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-t", str(duration),
                    "-an",
                    "-vf", "scale=320:-2",
                    "-c:v", "libvpx-vp9",
                    "-b:v", "200k",
                    "-deadline", "good",
                    "-cpu-used", "4",
                    str(preview_path)
                ],
                capture_output=True,
                text=True
            )

            # Clean up concat file
            concat_file.unlink()

            if result.returncode != 0:
                self.app.logger.warning(f"ffmpeg preview error: {result.stderr}")
                return False

            if preview_path.exists() and preview_path.stat().st_size > 0:
                self.app.logger.info(f"Generated preview from HLS segments: {preview_path}")
                return True
            else:
                self.app.logger.warning("Preview file not created or empty")
                return False

        except Exception as e:
            self.app.logger.warning(f"Failed to generate preview from HLS: {e}")
            return False

    def generate_thumbnail_from_hls(self, videos_folder: Path, filename: str, thumbnail_path: Path) -> bool:
        """Generate a thumbnail from an existing HLS video.

        Finds .ts segments directly by filename pattern and picks a random one.

        Args:
            videos_folder: Path to the videos folder
            filename: Base filename (without extension)
            thumbnail_path: Path where the thumbnail should be saved

        Returns:
            True if thumbnail was generated successfully, False otherwise
        """
        # Find quality-specific m3u8 files for this video to determine best quality
        quality_pattern = re.compile(rf'^{re.escape(filename)}_(\d+p)\.m3u8$')

        qualities = []
        for m3u8_file in videos_folder.glob(f'{filename}_*p.m3u8'):
            match = quality_pattern.match(m3u8_file.name)
            if match:
                quality_str = match.group(1)  # e.g., "720p"
                quality_num = int(quality_str.replace('p', ''))
                qualities.append((quality_num, quality_str))

        if not qualities:
            self.app.logger.warning(f"No quality variants found for {filename}")
            return False

        # Sort by resolution (descending) and pick the highest quality
        qualities.sort(key=lambda x: x[0], reverse=True)
        _, best_quality = qualities[0]  # e.g., "720p"

        # Find .ts segments directly by filename pattern (e.g., filename_720p_0000.ts)
        ts_pattern = f'{filename}_{best_quality}_*.ts'
        ts_files = sorted(videos_folder.glob(ts_pattern))

        if not ts_files:
            self.app.logger.warning(f"No .ts segments found matching {ts_pattern}")
            return False

        self.app.logger.info(f"Found {len(ts_files)} segments for {filename} at {best_quality}")

        # Pick a random segment (between 10% and 90% of the video)
        num_segments = len(ts_files)
        if num_segments > 2:
            start_idx = max(0, int(num_segments * 0.1))
            end_idx = min(num_segments - 1, int(num_segments * 0.9))
            selected_idx = random.randint(start_idx, end_idx)
        else:
            selected_idx = 0

        selected_ts = ts_files[selected_idx]
        self.app.logger.info(f"Selected segment {selected_ts.name}")

        # Generate thumbnail from the segment at a random offset
        try:
            # Get segment duration
            duration = self._get_video_duration(selected_ts)
            if duration > 1:
                offset = random.uniform(0.5, duration - 0.5)
            else:
                offset = 0

            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            # Note: -ss must come AFTER -i for .ts segments because they have
            # non-zero start timestamps. With -ss before -i, ffmpeg seeks from
            # absolute time 0, missing the segment's content entirely.
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(selected_ts), "-ss", str(offset),
                 "-vframes", "1", "-q:v", "2", str(thumbnail_path)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.app.logger.warning(f"ffmpeg error: {result.stderr}")
                return False

            if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
                self.app.logger.info(f"Generated thumbnail from {selected_ts.name}: {thumbnail_path}")
                return True
            else:
                self.app.logger.warning(f"Thumbnail file not created or empty")
                return False

        except Exception as e:
            self.app.logger.warning(f"Failed to generate thumbnail from HLS: {e}")
            return False

    def _encode_worker(self, job_id: int, input_path: Path, output_path: Path, qualities: list[str], delete_original: bool = True, thumbnail_path: Path = None, preview_path: Path = None):
        with self.app.app_context():
            job = db.session.get(EncodingJob, job_id)
            if not job:
                return

            job.status = "encoding"
            db.session.commit()

        self._progress[job_id] = {"progress": 0, "status": "encoding"}

        try:
            # Generate thumbnail before encoding
            if thumbnail_path:
                self._generate_thumbnail(input_path, thumbnail_path)

            # Generate preview video before encoding
            if preview_path:
                self._generate_preview(input_path, preview_path)

            video = ffmpeg_streaming.input(str(input_path))
            hls = video.hls(Formats.h264())

            representations = [QUALITY_PRESETS[q] for q in qualities if q in QUALITY_PRESETS]
            if not representations:
                representations = [QUALITY_PRESETS["360p"]]

            hls.representations(*representations)

            def monitor(ffmpeg, duration, time_, time_left, process):
                if duration > 0:
                    progress = min(round(time_ / duration * 100), 100)
                    self._progress[job_id] = {"progress": progress, "status": "encoding", "time_left": int(time_left)}

            self.app.logger.info(f"Starting encoding job {job_id}")
            hls.output(str(output_path), monitor=monitor)

            with self.app.app_context():
                job = db.session.get(EncodingJob, job_id)
                job.status = "completed"
                job.progress = 100
                job.completed_at = datetime.utcnow()
                db.session.commit()

            self._progress[job_id] = {"progress": 100, "status": "completed"}
            self.app.logger.info(f"Encoding job {job_id} completed")

            # Delete original MP4 file if requested
            if delete_original and input_path.exists():
                try:
                    input_path.unlink()
                    self.app.logger.info(f"Deleted original file: {input_path}")
                except Exception as e:
                    self.app.logger.warning(f"Failed to delete original file {input_path}: {e}")

        except Exception as e:
            self.app.logger.error(f"Encoding job {job_id} failed: {e}")
            with self.app.app_context():
                job = db.session.get(EncodingJob, job_id)
                job.status = "failed"
                job.error_message = str(e)
                db.session.commit()
            self._progress[job_id] = {"progress": 0, "status": "failed", "error": str(e)}


encoder_service = EncoderService()
