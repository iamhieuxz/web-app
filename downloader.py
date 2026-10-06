"""Wrapper cho gallery-dl và yt-dlp subprocess.

Các hàm trong module này đều là generator yield từng dòng stdout,
để service layer có thể parse real-time và đưa qua rate-limit guard.
"""
from __future__ import annotations

import logging
import os
from typing import Iterator

from process_manager import ProcessManager

logger = logging.getLogger("downloader")


class Downloader:
    def __init__(self, pm: ProcessManager) -> None:
        self.pm = pm

    def execute_ig_download(
        self,
        url: str,
        dest: str,
        cookie: str,
        limit_range: str | None = None,
        disable_range: bool = True,
        prefix: str = "",
        extra_args: list[str] | None = None,
    ) -> Iterator[str]:
        cmd = ["python", "-m", "gallery_dl", "--destination", os.path.abspath(dest)]
        archive_path = os.path.abspath(os.path.join(dest, ".instagram_archive.sqlite"))
        cmd.extend(["--download-archive", archive_path])

        if cookie and os.path.exists(cookie):
            cmd.extend(["--cookies", os.path.abspath(cookie)])

        if limit_range:
            cmd.extend(["--range", limit_range])
        elif disable_range:
            cmd.extend(["--range", "1-"])

        # Cấu trúc tên file: [TIỀN TỐ]_[NGÀY]_[SHORTCODE/ID]_[SỐ THỨ TỰ 4 CHỮ SỐ].[EXT]
        filename_template = (
            f"{prefix}{{date:%Y-%m-%d}}_{{shortcode|id}}_{{num:04d}}.{{extension}}"
        )
        cmd.extend(["--filename", filename_template])

        if extra_args:
            cmd.extend(extra_args)

        # Các tham số chống Rate Limit (giống x_tool3.py)
        cmd.extend(["--sleep-request", "3-10"])
        cmd.extend(["--sleep", "1-5"])
        cmd.extend(["-o", "cache.file=none"])

        cmd.append(url)

        try:
            self.pm.start(cmd)
        except FileNotFoundError:
            logger.error("Không tìm thấy 'gallery-dl' trong PATH")
            return
        yield from self.pm.iter_stdout()

    def execute_twitter_download(
        self, url: str, dest: str, cookie: str
    ) -> Iterator[str]:
        cmd = ["python", "-m", "gallery_dl", "--destination", os.path.abspath(dest)]
        archive_path = os.path.abspath(os.path.join(dest, ".twitter_archive.sqlite"))
        cmd.extend(["--download-archive", archive_path])

        if cookie and os.path.exists(cookie):
            cmd.extend(["--cookies", os.path.abspath(cookie)])

        # Tên file Twitter: [NGÀY]_[TWEET_ID]_[SỐ THỨ TỰ 4 CHỮ SỐ].[EXT]
        filename_template = (
            "{date:%Y-%m-%d}_{tweet_id|id}_{num:04d}.{extension}"
        )
        cmd.extend(["--filename", filename_template])

        # Các tham số chống Rate Limit (giống tool cũ x_tool3.py)
        cmd.extend(["--sleep-request", "3-10"])
        cmd.extend(["--sleep", "1-5"])
        cmd.extend(["-o", "cache.file=none"])

        cmd.append(url)

        try:
            self.pm.start(cmd)
        except FileNotFoundError:
            logger.error("Không tìm thấy 'gallery-dl' trong PATH")
            return
        yield from self.pm.iter_stdout()

    def execute_ytdlp(
        self, url: str, dest: str, cookie: str
    ) -> Iterator[str]:
        cmd = ["yt-dlp", "-P", os.path.abspath(dest), "--print", "%(title)s"]
        if cookie and os.path.exists(cookie):
            cmd.extend(["--cookies", os.path.abspath(cookie)])
        cmd.append(url)

        try:
            self.pm.start(cmd)
        except FileNotFoundError:
            logger.error("Không tìm thấy 'yt-dlp' trong PATH")
            return
        yield from self.pm.iter_stdout()
