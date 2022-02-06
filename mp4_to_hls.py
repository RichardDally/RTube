import sys
import datetime
import ffmpeg_streaming
from loguru import logger
from ffmpeg_streaming import Formats, Representation, Size, Bitrate


_144p = Representation(Size(256, 144), Bitrate(95 * 1024, 64 * 1024))
_240p = Representation(Size(426, 240), Bitrate(150 * 1024, 94 * 1024))
_360p = Representation(Size(640, 360), Bitrate(276 * 1024, 128 * 1024))
_480p = Representation(Size(854, 480), Bitrate(750 * 1024, 192 * 1024))
_720p = Representation(Size(1280, 720), Bitrate(2048 * 1024, 320 * 1024))
_1080p = Representation(Size(1920, 1080), Bitrate(4096 * 1024, 320 * 1024))
_2k = Representation(Size(2560, 1440), Bitrate(6144 * 1024, 320 * 1024))
_4k = Representation(Size(3840, 2160), Bitrate(17408 * 1024, 320 * 1024))


def monitor(ffmpeg, duration, time_, time_left, process):
    per = round(time_ / duration * 100)
    sys.stdout.write(
        "\rTranscoding...(%s%%) %s left [%s%s]" %
        (per, datetime.timedelta(seconds=int(time_left)), '#' * per, '-' * (100 - per))
    )
    sys.stdout.flush()


def mp4_to_hls():
    video = ffmpeg_streaming.input(r"static/Gameplay.mp4")
    hls = video.hls(Formats.h264())
    hls.auto_generate_representations()
    # hls.representations(_1080p)
    # logger.info("Encoding will start now.")
    hls.output(r"static/videos/hls.m3u8", monitor=monitor)
    # logger.info("Encoding has ended.")


mp4_to_hls()
