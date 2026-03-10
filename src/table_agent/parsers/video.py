"""视频关键帧提取解析器"""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np

from ..models import ParsedContent


class VideoParser:
    """提取视频关键帧为 base64 图片"""

    SUPPORTED = {"mp4", "avi", "mov", "mkv", "webm"}

    def __init__(self, max_frames: int = 10, interval_sec: float = 2.0):
        self.max_frames = max_frames
        self.interval_sec = interval_sec

    def parse(self, file_path: str) -> ParsedContent:
        """解析视频文件，提取关键帧"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        frames, video_meta = self._extract_frames(str(path))
        images = [self._frame_to_base64(f) for f in frames]

        metadata = {
            "file_name": path.name,
            "file_size": path.stat().st_size,
            "frame_count": len(images),
            **video_meta,
        }

        return ParsedContent(
            source_path=str(path.resolve()),
            file_type="mp4",
            images=images,
            metadata=metadata,
        )

    def _extract_frames(self, path: str) -> tuple[list[np.ndarray], dict]:
        """使用 OpenCV 按间隔抽取关键帧"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频: {path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        frame_interval = int(fps * self.interval_sec)

        video_meta = {
            "fps": fps,
            "total_frames": total_frames,
            "duration_sec": round(duration, 2),
        }

        frames: list[np.ndarray] = []
        frame_idx = 0

        while len(frames) < self.max_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
            frame_idx += frame_interval

        cap.release()
        return frames, video_meta

    @staticmethod
    def _frame_to_base64(frame: np.ndarray) -> str:
        """将 OpenCV 帧转为 base64 JPEG"""
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

    @classmethod
    def supports(cls, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower().lstrip(".")
        return ext in cls.SUPPORTED
