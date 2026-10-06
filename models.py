from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set
from pydantic import BaseModel

@dataclass(slots=True)
class AppConfig:
    download_folder: str = "/data/downloads"
    cookie_path: str = ""
    backup_cookie_path: str = ""
    cookie_x_path: str = ""

    @property
    def instagram_folder(self) -> str:
        return os.path.join(self.download_folder, "instagram")

    @property
    def twitter_folder(self) -> str:
        return os.path.join(self.download_folder, "twitter")

    def normalized_download_folder(self) -> str:
        return str(Path(self.download_folder).expanduser().resolve())


@dataclass
class RuntimeState:
    """Trạng thái runtime chia sẻ giữa các thread.

    - `is_tool_unlocked`: cookie đã sẵn sàng chưa
    - `stop_event`: threading.Event — an toàn khi set/check giữa các thread
      (thay thế cho bool `stop_requested` cũ để tránh race condition)
    - các cache set dùng cho logic 3 chế độ cache
    """
    is_tool_unlocked: bool = False
    _stop_event: threading.Event = field(default_factory=threading.Event)
    cache_them_moi: Set[str] = field(default_factory=set)
    cache_cap_nhat_all: Set[str] = field(default_factory=set)
    cache_cap_nhat_nhanh: Set[str] = field(default_factory=set)

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    @stop_requested.setter
    def stop_requested(self, value: bool) -> None:
        if value:
            self._stop_event.set()
        else:
            self._stop_event.clear()

    def request_stop(self) -> None:
        """Helper: set stop event."""
        self._stop_event.set()

    def clear_stop(self) -> None:
        """Helper: xoá stop event (bắt đầu job mới)."""
        self._stop_event.clear()


class SingleTargetRequest(BaseModel):
    target: str
    disable_range: bool = True
    include_posts: bool = True
    include_stories: bool = True
    include_highlights: bool = False


class ListTargetRequest(BaseModel):
    targets: list[str] = []
    disable_range: bool = True
    include_posts: bool = True
    include_stories: bool = True
    include_highlights: bool = False


class LiveRequest(BaseModel):
    target: str