"""Service layer: business logic cho Instagram và Twitter/X.

Các method ở đây đều chạy trên worker thread (từ ThreadPoolExecutor trong web_server),
nên phải cẩn thận với shared state (state_ig / state_x).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import database
import utils
from downloader import Downloader
from models import AppConfig, RuntimeState
from rate_limit import RateLimitGuard

logger = logging.getLogger("services")

# Mở rộng thêm các định dạng hiện đại
IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".avif",
    ".mp4", ".mov", ".webm", ".mkv",
)

# ==========================================
# DỊCH VỤ INSTAGRAM
# ==========================================
class InstagramService:
    def __init__(
        self,
        downloader: Downloader,
        rate_limit_guard: RateLimitGuard,
        app_config: AppConfig,
        state: RuntimeState,
        log_callback: Callable[[str, str], None] | None = None,
    ):
        self.downloader = downloader
        self.rate_limit_guard = rate_limit_guard
        self.app_config = app_config
        self.state = state
        self.log = log_callback or (lambda msg, tag="LOG_NORMAL": None)

    def _clear_instagram_cache(self) -> None:
        try:
            subprocess.run(
                ["gallery-dl", "--clear-cache", "instagram"],
                capture_output=True, timeout=10,
            )
        except Exception:
            logger.debug("Không xoá được cache IG (có thể chưa cài gallery-dl)")

    def _resolve_author_username(self, target_url: str) -> str | None:
        """Truy vấn gallery-dl để lấy username thật của chủ bài viết."""
        cookie = self.app_config.cookie_path
        cmd = ["gallery-dl", "--range", "1", "--print", "{username}"]
        if cookie and os.path.exists(cookie):
            cmd.extend(["--cookies", os.path.abspath(cookie)])
        cmd.append(target_url)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        si = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1

        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                startupinfo=si,
                env=env,
            )
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    val = line.strip()
                    # Username hợp lệ: không có space, không comment, không log gallery-dl
                    if val and not val.startswith("#") and not val.startswith("[") and " " not in val:
                        clean_u = utils.clean_username(val)
                        if clean_u:
                            return clean_u
        except subprocess.TimeoutExpired:
            logger.warning("Timeout khi resolve author username cho %s", target_url)
        except Exception as e:
            self.log(
                f"   ℹ️ Không thể truy vấn username tác giả ({e}), lưu theo mã bài viết.",
                "LOG_NORMAL",
            )
        return None

    def _derive_destination_name(self, target: str) -> str:
        cleaned = (
            target.strip()
            .replace("https://www.instagram.com/", "")
            .replace("https://instagram.com/", "")
            .split("?")[0]
            .split("#")[0]
            .strip("/")
        )
        parts = [p for p in cleaned.split("/") if p]
        if not parts:
            return "instagram"

        if self._is_single_post_target(target):
            self.log("🔍 Đang nhận diện chủ sở hữu của bài viết...", "LOG_SYSTEM")
            resolved_user = self._resolve_author_username(target)
            if resolved_user and utils.is_valid_username(resolved_user):
                self.log(
                    f"🎯 Đã tìm thấy tác giả: @{resolved_user} "
                    f"(Gom bài vào thư mục: @{resolved_user})",
                    "FILE_NEW",
                )
                return resolved_user
            return utils.clean_username(parts[-1]) or "instagram"

        if parts[0] == "stories" and len(parts) > 1:
            return utils.clean_username(parts[1]) or "instagram"

        return utils.clean_username(parts[0]) or "instagram"

    def download_single_new(self, user: str, disable_range: bool) -> None:
        try:
            self._clear_instagram_cache()
            target = self._normalize_instagram_target(user)
            dest_name = self._derive_destination_name(target)
            dest = os.path.join(self.app_config.instagram_folder, dest_name)
            os.makedirs(dest, exist_ok=True)
            limit_range = None if disable_range else (
                "1-4" if self._is_single_post_target(target) else None
            )

            self.log(f"➕ [IG] Thêm mới vào hồ sơ: @{dest_name}", "LOG_SYSTEM")

            saw, had_error = self._consume_download(
                url=target,
                dest=dest,
                limit_range=limit_range,
                disable_range=disable_range,
                label="POST",
                log_new_only=False,
            )

            database.update_last_synced(dest_name)

            if had_error:
                self.log(
                    "⚠️ Quá trình tải gặp lỗi, vui lòng kiểm tra dòng báo lỗi chi tiết bên trên.",
                    "LOG_WARN",
                )
            elif not saw and not self.state.stop_requested:
                self.log("   ⏭ Thư mục profile đã đồng bộ đầy đủ dữ liệu.", "FILE_OLD")

            self.log(f"🎉 [IG] Hoàn tất bài viết vào thư mục @{dest_name}!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi download_single_new")
            self.log(f"⚠️️ [IG Ngoại lệ]: {e}", "LOG_WARN")

    def download_list_new(self, targets: list[str], disable_range: bool) -> None:
        try:
            valid_targets = [t.strip() for t in targets if t and t.strip()]
            if not valid_targets:
                return

            self._clear_instagram_cache()
            self.log(f"🚀 [IG] Quét danh sách {len(valid_targets)} mục tiêu...", "LOG_SYSTEM")

            for index, raw_target in enumerate(valid_targets, start=1):
                if self.state.stop_requested:
                    break

                target_url = self._normalize_instagram_target(raw_target)
                dest_name = self._derive_destination_name(raw_target)
                dest = os.path.join(self.app_config.instagram_folder, dest_name)
                os.makedirs(dest, exist_ok=True)

                self.log(
                    f"🌐 [{index}/{len(valid_targets)}] Đang lưu vào thư mục: @{dest_name}",
                    "LOG_SYSTEM",
                )

                saw, had_error = self._consume_download(
                    url=target_url,
                    dest=dest,
                    limit_range=None,
                    disable_range=disable_range,
                    label="POST",
                    log_new_only=False,
                )

                database.update_last_synced(dest_name)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log("🎉 [IG] QUÉT DANH SÁCH HOÀN THÀNH!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi download_list_new")
            self.log(f"⚠️ [IG Ngoại lệ]: {e}", "LOG_WARN")

    def update_single(
        self,
        target: str,
        disable_range: bool,
        include_posts: bool = True,
        include_stories: bool = True,
        include_highlights: bool = False,
    ) -> None:
        try:
            self._clear_instagram_cache()
            target_url = self._normalize_instagram_target(target)
            dest_name = self._derive_destination_name(target_url)
            dest = os.path.join(self.app_config.instagram_folder, dest_name)
            os.makedirs(dest, exist_ok=True)

            self.log(f"🚀 [IG] Cập nhật vào thư mục: @{dest_name}", "LOG_SYSTEM")
            self._run_layered_sync(
                target=target_url,
                dest=dest,
                disable_range=disable_range,
                include_posts=include_posts,
                include_stories=include_stories,
                include_highlights=include_highlights,
            )
            database.update_last_synced(dest_name)
            self.log(f"🎉 [IG] Hoàn tất cập nhật @{dest_name}!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi update_single")
            self.log(f"⚠️ [IG Ngoại lệ]: {e}", "LOG_WARN")

    def update_list(
        self,
        targets: list[str],
        disable_range: bool,
        include_posts: bool = True,
        include_stories: bool = True,
        include_highlights: bool = False,
    ) -> None:
        try:
            valid_targets = [t.strip() for t in targets if t and t.strip()]
            if not valid_targets:
                return

            self._clear_instagram_cache()
            self.log(
                f"🚀 [IG CẬP NHẬT LIST] Bắt đầu xử lý cho {len(valid_targets)} mục tiêu...",
                "LOG_SYSTEM",
            )

            for index, raw_target in enumerate(valid_targets, start=1):
                if self.state.stop_requested:
                    break

                target_url = self._normalize_instagram_target(raw_target)
                dest_name = self._derive_destination_name(raw_target)
                dest = os.path.join(self.app_config.instagram_folder, dest_name)
                os.makedirs(dest, exist_ok=True)

                self.log(
                    f"🔄 [{index}/{len(valid_targets)}] Cập nhật thư mục: @{dest_name}",
                    "LOG_SYSTEM",
                )
                self._run_layered_sync(
                    target=target_url,
                    dest=dest,
                    disable_range=disable_range,
                    include_posts=include_posts,
                    include_stories=include_stories,
                    include_highlights=include_highlights,
                )

                database.update_last_synced(dest_name)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log("🎉 [IG] CẬP NHẬT DANH SÁCH HOÀN THÀNH!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi update_list")
            self.log(f"⚠️ [IG Ngoại lệ]: {e}", "LOG_WARN")

    def sync_all_local(self) -> None:
        try:
            root_path = Path(self.app_config.instagram_folder)
            if not root_path.exists():
                root_path.mkdir(parents=True, exist_ok=True)
            subfolders = [p.name for p in root_path.iterdir() if p.is_dir()]
            self.log(
                f"🚀 [IG] Phát hiện {len(subfolders)} thư mục. Kích hoạt càn quét đồng bộ...",
                "LOG_SYSTEM",
            )

            self._clear_instagram_cache()
            for index, folder in enumerate(subfolders, start=1):
                if self.state.stop_requested:
                    break
                dest = os.path.join(self.app_config.instagram_folder, folder)
                self.log(f"📥 [{index}/{len(subfolders)}] IG: @{folder}", "LOG_SYSTEM")

                self._consume_download(
                    f"https://www.instagram.com/{folder}",
                    dest, limit_range=None, disable_range=True,
                    label="POST", log_new_only=True,
                )
                if not self.state.stop_requested:
                    self._consume_download(
                        f"https://www.instagram.com/stories/{folder}",
                        dest, limit_range=None, disable_range=True,
                        label="STORY", log_new_only=True,
                    )

                database.update_last_synced(folder)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log("🎉 [IG] ĐỒNG BỘ ĐỒNG LOẠT HOÀN THÀNH!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi sync_all_local")
            self.log(f"⚠️ [IG Ngoại lệ]: {e}", "LOG_WARN")

    def _run_layered_sync(
        self,
        *,
        target: str,
        dest: str,
        disable_range: bool,
        include_posts: bool,
        include_stories: bool,
        include_highlights: bool,
    ) -> None:
        if include_posts:
            self.log("📝 Lớp 1: Timeline Feed...", "LOG_SYSTEM")
            saw, had_error = self._consume_download(
                target, dest, limit_range=None,
                disable_range=disable_range, label="POST", log_new_only=False,
            )
            if not saw and not had_error and not self.state.stop_requested:
                self.log("   ℹ️️ Không có bài viết mới trên Timeline.", "FILE_OLD")

        if self.state.stop_requested or self._is_single_post_target(target):
            return

        if include_stories:
            self.log("📸 Lớp 2: Stories (24h)...", "LOG_SYSTEM")
            saw, had_error = self._consume_download(
                self._stories_url(target), dest, limit_range=None,
                disable_range=disable_range, label="STORY", log_new_only=False,
            )
            if not saw and not had_error and not self.state.stop_requested:
                self.log("   ℹ️ Không có Story mới trong 24h qua.", "FILE_OLD")

        if self.state.stop_requested:
            return

        if include_highlights:
            self.log("⭐ Lớp 3: Highlights...", "LOG_SYSTEM")
            # Kiểm tra URL: dạng /stories/highlights/<ID>/ là highlight cụ thể
            # Ngược lại, scrape highlight IDs từ profile
            if "/stories/highlights/" in target and not target.endswith("/highlights/"):
                # URL cụ thể: https://www.instagram.com/stories/highlights/<HL_ID>/
                hl_url = target.rstrip("/") + "/"
                saw, had_error = self._consume_download(
                    hl_url, dest, limit_range=None,
                    disable_range=disable_range, label="HIGHLIGHT", log_new_only=False,
                )
            else:
                # URL tổng hợp: https://www.instagram.com/{username}/highlights/
                # Cần scrape để lấy từng highlight reel ID
                hl_username = self._derive_destination_name(self._normalize_instagram_target(target))
                self.log(f"   🔍 Đang tìm highlights của @{hl_username}...", "LOG_NORMAL")
                
                highlight_ids = self._get_highlight_ids_from_username(hl_username)
                
                if not highlight_ids:
                    # Fallback: thử trực tiếp URL highlights
                    self.log("   ⚠️ Không lấy được highlight IDs, thử URL trực tiếp...", "LOG_NORMAL")
                    highlights_url = f"https://www.instagram.com/{hl_username}/highlights/"
                    saw, had_error = self._consume_download(
                        highlights_url, dest, limit_range=None,
                        disable_range=disable_range, label="HIGHLIGHT", log_new_only=False,
                    )
                else:
                    self.log(f"   📋 Tìm thấy {len(highlight_ids)} nhóm Highlight!", "LOG_NORMAL")
                    any_saw = False
                    any_error = False
                    for idx, hl_id in enumerate(highlight_ids, start=1):
                        if self.state.stop_requested:
                            break
                        hl_url = f"https://www.instagram.com/stories/highlights/{hl_id}/"
                        self.log(f"   ⭐ [{idx}/{len(highlight_ids)}] Đang tải Highlight {hl_id}...", "LOG_NORMAL")
                        saw, had_error = self._consume_download(
                            hl_url, dest, limit_range=None,
                            disable_range=disable_range, label="HIGHLIGHT", log_new_only=False,
                        )
                        any_saw = any_saw or saw
                        any_error = any_error or had_error
                        if idx < len(highlight_ids):
                            self.rate_limit_guard.wait_after_account(
                                stop_requested=lambda: self.state.stop_requested
                            )
                    saw, had_error = any_saw, any_error
                    
            if not saw and not had_error and not self.state.stop_requested:
                self.log(
                    "   ℹ️ Tài khoản không có Highlight hoặc đã đồng bộ đầy đủ.",
                    "FILE_OLD",
                )

    def _consume_download(
        self,
        url: str,
        dest: str,
        limit_range: str | None,
        disable_range: bool,
        label: str,
        log_new_only: bool,
        extra_args: list[str] | None = None,
    ) -> tuple[bool, bool]:
        saw_media = False
        had_error = False
        prefix = "STORY_" if label == "STORY" else "HL_" if label == "HIGHLIGHT" else ""

        for line in self._download_with_cookie_fallback(
            url, dest,
            limit_range=limit_range,
            disable_range=disable_range,
            source=label,
            prefix=prefix,
            extra_args=extra_args,
        ):
            if self.state.stop_requested:
                break
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()

            if self.rate_limit_guard.detect_limit_signal(lowered):
                if self.rate_limit_guard.record_limit_signal(label):
                    self.log("🛑 Tạm dừng tác vụ do quá giới hạn.", "LOG_WARN")
                    self.state.request_stop()
                    self.downloader.pm.stop()
                    break
                self.rate_limit_guard.wait_after_limit_signal(
                    stop_requested=lambda: self.state.stop_requested
                )
                continue

            if any(ext in lowered for ext in IMAGE_EXTENSIONS):
                saw_media = True
                is_new = not stripped.startswith("#")
                clean_path = stripped.lstrip("#").strip()
                if is_new:
                    self.log(
                        f"   [NEW {label}] -> {os.path.basename(clean_path)}",
                        "FILE_NEW",
                    )
                else:
                    if not log_new_only:
                        self.log(
                            f"   [ĐÃ CÓ {label}] • {os.path.basename(clean_path)}",
                            "FILE_OLD",
                        )
                continue

            if any(err_kw in lowered for err_kw in (
                "[error]", "error:", "httperror", "redirect",
                "401", "404", "unauthorized",
            )):
                had_error = True
                self.log(f"   ❌ {stripped}", "LOG_WARN")
                continue

            if "[warning]" in lowered:
                self.log(f"   ⚠️ {stripped}", "LOG_WARN")
                continue

            if not stripped.startswith("#"):
                self.log(f"   ℹ️ {stripped}", "LOG_NORMAL")

        return saw_media, had_error

    def _download_with_cookie_fallback(
        self,
        url: str,
        dest: str,
        limit_range: str | None = None,
        disable_range: bool = True,
        source: str = "POST",
        prefix: str = "",
        extra_args: list[str] | None = None,
    ) -> Any:
        cookie_paths = [self.app_config.cookie_path]
        if (
            self.app_config.backup_cookie_path
            and self.app_config.backup_cookie_path != self.app_config.cookie_path
        ):
            cookie_paths.append(self.app_config.backup_cookie_path)

        for index, cookie in enumerate(cookie_paths, start=1):
            saw_limit = False
            for line in self.downloader.execute_ig_download(
                url, dest, cookie,
                limit_range, disable_range, prefix, extra_args=extra_args,
            ):
                if self.rate_limit_guard.detect_limit_signal(line):
                    saw_limit = True
                yield line
                if self.state.stop_requested:
                    return
            if not saw_limit:
                return
            if index < len(cookie_paths) and not self.state.stop_requested:
                self.log("⚠️ Thử lại bằng cookie dự phòng...", "LOG_WARN")
                self.rate_limit_guard.wait_after_limit_signal(
                    stop_requested=lambda: self.state.stop_requested
                )

    def _normalize_instagram_target(self, target: str) -> str:
        cleaned = (
            target.strip()
            .replace("https://www.instagram.com/", "")
            .replace("https://instagram.com/", "")
            .split("?")[0]
            .split("#")[0]
            .strip("/")
        )
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            return cleaned.rstrip("/")
        return f"https://www.instagram.com/{cleaned}"

    def _is_single_post_target(self, target: str) -> bool:
        return any(marker in target for marker in ("/p/", "/reel/", "/reels/", "/tv/"))

    def _stories_url(self, target: str) -> str:
        return (
            f"https://www.instagram.com/stories/"
            f"{self._derive_destination_name(self._normalize_instagram_target(target))}"
        )

    def _get_highlight_ids_from_username(self, username: str) -> list[str]:
        """Scrape highlight IDs từ username bằng cách dùng gallery-dl với URL tổng hợp.
        
        Returns list of highlight IDs (reel IDs).
        """
        import json
        import re
        
        cookie = self.app_config.cookie_path
        cmd = [
            "gallery-dl",
            "--cookies", os.path.abspath(cookie) if cookie else "",
            "--json",
            f"https://www.instagram.com/{username}/highlights/"
        ]
        
        # Filter out empty cookie arg if no cookie
        cmd = [c for c in cmd if c]
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        si = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1
        
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                startupinfo=si,
                env=env,
            )
            
            # Parse JSON output từ gallery-dl
            highlight_ids = []
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Tìm highlight reel ID trong JSON
                    if isinstance(data, dict):
                        # Kiểm tra various possible key names
                        for key in ('id', 'highlightId', 'reel_id', 'highlight_id'):
                            if key in data and isinstance(data[key], str):
                                hl_id = data[key]
                                if hl_id.isdigit() and len(hl_id) >= 15:
                                    highlight_ids.append(hl_id)
                except json.JSONDecodeError:
                    continue
            
            # Fallback: parse từ text output nếu không có JSON
            if not highlight_ids:
                output = proc.stderr + proc.stdout
                # Tìm patterns như: "highlight_reel_123456789012345"
                matches = re.findall(r'highlight[_\s]reel[_\s]?(\d{15,20})', output, re.IGNORECASE)
                highlight_ids.extend(matches)
                
                # Hoặc tìm URL patterns
                url_matches = re.findall(r'highlights/(\d{15,20})', output)
                highlight_ids.extend(url_matches)
            
            return list(set(highlight_ids))
            
        except subprocess.TimeoutExpired:
            logger.warning("Timeout khi lấy highlight IDs cho %s", username)
        except Exception as e:
            logger.warning("Lỗi khi lấy highlight IDs cho %s: %s", username, e)
        
        return []


# ==========================================
# DỊCH VỤ TWITTER / X
# ==========================================
class TwitterService:
    def __init__(
        self,
        downloader: Downloader,
        rate_limit_guard: RateLimitGuard,
        app_config: AppConfig,
        state: RuntimeState,
        log_callback: Callable[[str, str], None] | None = None,
    ):
        self.downloader = downloader
        self.rate_limit_guard = rate_limit_guard
        self.app_config = app_config
        self.state = state
        self.log = log_callback or (lambda msg, tag="LOG_NORMAL": None)

    def _clear_twitter_cache(self) -> None:
        try:
            subprocess.run(
                ["gallery-dl", "--clear-cache", "twitter"],
                capture_output=True, timeout=10,
            )
        except Exception:
            logger.debug("Không xoá được cache Twitter")

    def _derive_twitter_name(self, target: str) -> str:
        cleaned = (
            target.strip()
            .replace("https://twitter.com/", "")
            .replace("https://x.com/", "")
            .split("?")[0]
            .split("#")[0]
            .strip("/")
        )
        parts = [p for p in cleaned.split("/") if p]
        if not parts:
            return "twitter"
        return utils.clean_username(parts[0]) or "twitter"

    def download_single(self, target: str) -> None:
        try:
            self._clear_twitter_cache()
            target_url = self._normalize_twitter_target(target)
            dest_name = self._derive_twitter_name(target)
            dest = os.path.join(self.app_config.twitter_folder, dest_name)
            os.makedirs(dest, exist_ok=True)

            self.log(f"➕ [X] Bắt đầu tải mục tiêu: @{dest_name}", "LOG_SYSTEM")
            self._consume_x_download(target_url, dest)
            database.update_last_synced(dest_name)
            self.log(f"🎉 [X] Đã hoàn thành tác vụ cho @{dest_name}!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi download_single")
            self.log(f"⚠️ [X Ngoại lệ]: {e}", "LOG_WARN")

    def update_single(self, target: str) -> None:
        try:
            self._clear_twitter_cache()
            target_url = self._normalize_twitter_target(target)
            dest_name = self._derive_twitter_name(target)
            dest = os.path.join(self.app_config.twitter_folder, dest_name)
            os.makedirs(dest, exist_ok=True)

            self.log(
                f"🚀 [X] Kiểm tra cập nhật bài viết mới: @{dest_name}", "LOG_SYSTEM",
            )
            self._consume_x_download(target_url, dest)
            database.update_last_synced(dest_name)
            self.log(f"🎉 [X] Đã cập nhật xong cho @{dest_name}!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi update_single")
            self.log(f"⚠️ [X Ngoại lệ]: {e}", "LOG_WARN")

    def download_list(self, targets: list[str]) -> None:
        try:
            valid_targets = [t.strip() for t in targets if t and t.strip()]
            if not valid_targets:
                self.log("⚠️ [X] Danh sách tài khoản trống!", "LOG_WARN")
                return

            self._clear_twitter_cache()
            self.log(
                f"🚀 [X] Bắt đầu quét danh sách {len(valid_targets)} tài khoản...",
                "LOG_SYSTEM",
            )

            for index, raw_target in enumerate(valid_targets, start=1):
                if self.state.stop_requested:
                    break

                target_url = self._normalize_twitter_target(raw_target)
                dest_name = self._derive_twitter_name(raw_target)
                dest = os.path.join(self.app_config.twitter_folder, dest_name)
                os.makedirs(dest, exist_ok=True)

                self.log(
                    f"🌐 [{index}/{len(valid_targets)}] Đang xử lý tài khoản X: @{dest_name}",
                    "LOG_SYSTEM",
                )
                self._consume_x_download(target_url, dest)

                database.update_last_synced(dest_name)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log("🎉 [X] QUÉT DANH SÁCH HOÀN THÀNH!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi download_list")
            self.log(f"⚠️ [X Ngoại lệ]: {e}", "LOG_WARN")

    def update_list(self, targets: list[str]) -> None:
        try:
            valid_targets = [t.strip() for t in targets if t and t.strip()]
            if not valid_targets:
                self.log("⚠️ [X] Danh sách tài khoản trống!", "LOG_WARN")
                return

            self._clear_twitter_cache()
            self.log(
                f"🚀 [X] Bắt đầu cập nhật danh sách {len(valid_targets)} tài khoản...",
                "LOG_SYSTEM",
            )

            for index, raw_target in enumerate(valid_targets, start=1):
                if self.state.stop_requested:
                    break

                target_url = self._normalize_twitter_target(raw_target)
                dest_name = self._derive_twitter_name(raw_target)
                dest = os.path.join(self.app_config.twitter_folder, dest_name)
                os.makedirs(dest, exist_ok=True)

                self.log(
                    f"🔄 [{index}/{len(valid_targets)}] Cập nhật tài khoản X: @{dest_name}",
                    "LOG_SYSTEM",
                )
                self._consume_x_download(target_url, dest)

                database.update_last_synced(dest_name)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log("🎉 [X] CẬP NHẬT DANH SÁCH HOÀN THÀNH!", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi update_list")
            self.log(f"⚠️ [X Ngoại lệ]: {e}", "LOG_WARN")

    def sync_all_local(self) -> None:
        try:
            root_path = Path(self.app_config.twitter_folder)
            if not root_path.exists():
                root_path.mkdir(parents=True, exist_ok=True)
            subfolders = [
                p.name for p in root_path.iterdir()
                if p.is_dir() and p.name != "Livestreams_X"
            ]

            if not subfolders:
                self.log(
                    "⚠️ [X] Thư mục X trống, chưa có tài khoản nào dưới local để cập nhật.",
                    "LOG_WARN",
                )
                return

            self._clear_twitter_cache()
            self.log(
                f"🚀 [X] Phát hiện {len(subfolders)} thư mục dưới local. Kích hoạt càn quét đồng bộ...",
                "LOG_SYSTEM",
            )

            for index, folder in enumerate(subfolders, start=1):
                if self.state.stop_requested:
                    break
                dest = os.path.join(self.app_config.twitter_folder, folder)

                self.log(
                    f"📥 [{index}/{len(subfolders)}] Đang quét tài khoản X: @{folder}",
                    "LOG_SYSTEM",
                )
                self._consume_x_download(f"https://twitter.com/{folder}/media", dest)

                database.update_last_synced(folder)
                self.rate_limit_guard.wait_after_account(
                    stop_requested=lambda: self.state.stop_requested
                )

            self.log(
                "🎉 [X] TIẾN TRÌNH ĐỒNG BỘ TOÀN BỘ HOÀN THÀNH!", "LOG_SYSTEM",
            )
        except Exception as e:
            logger.exception("Lỗi sync_all_local")
            self.log(f"⚠️ [X Ngoại lệ]: {e}", "LOG_WARN")

    def download_livestream(self, url: str) -> None:
        try:
            dest = os.path.join(self.app_config.twitter_folder, "Livestreams_X")
            os.makedirs(dest, exist_ok=True)
            self.log("🎥 [X-LIVE] Bắt đầu kết nối tải luồng Livestream...", "LOG_SYSTEM")

            cookie = self.app_config.cookie_x_path
            for line in self.downloader.execute_ytdlp(url, dest, cookie):
                if self.state.stop_requested:
                    break
                if "[download]" in line or "[twitter" in line:
                    self.log(f"   {line.strip()}", "LOG_NORMAL")
            self.log("✅ [X-LIVE] Đã kết thúc tiến trình yt-dlp.", "LOG_SYSTEM")
        except Exception as e:
            logger.exception("Lỗi download_livestream")
            self.log(f"⚠️️ [X-LIVE Lỗi]: {e}", "LOG_WARN")

    # Các extension file media đầy đủ hơn
    _X_MEDIA_EXT = IMAGE_EXTENSIONS

    def _consume_x_download(self, url: str, dest: str) -> None:
        local_count = 0
        if os.path.exists(dest):
            for _, _, files in os.walk(dest):
                # Chỉ đếm file media, bỏ archive/ẩn
                local_count += sum(
                    1 for f in files
                    if not f.startswith(".")
                    and not f.endswith((".sqlite", ".sqlite3", ".tmp"))
                )

        self.log(f"📁 Thư mục local hiện có: {local_count} tệp", "LOG_SYSTEM")

        cookie = self.app_config.cookie_x_path
        if not cookie or not os.path.exists(cookie):
            self.log(
                "⚠️ [X Cảnh báo]: Chưa có Cookie X hoặc Cookie chưa được nạp. "
                "Hãy chọn tệp cookie ở BƯỚC 1.",
                "LOG_WARN",
            )
            return

        new_count = 0
        for line in self.downloader.execute_twitter_download(url, dest, cookie):
            if self.state.stop_requested:
                break
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()

            if "rate limit" in lowered or "429" in lowered:
                self.log("🛑 [X] Trúng Rate Limit (429). Đang chờ giãn nhịp...", "LOG_WARN")
                self.rate_limit_guard.wait_after_limit_signal(
                    stop_requested=lambda: self.state.stop_requested
                )
                continue

            if any(ext in lowered for ext in self._X_MEDIA_EXT):
                is_new = not stripped.startswith("#")
                clean_path = stripped.lstrip("#").strip()
                if is_new:
                    new_count += 1
                    self.log(
                        f"   [NEW TWEET] -> {os.path.basename(clean_path)}",
                        "FILE_NEW",
                    )
                else:
                    self.log(
                        f"   [ĐÃ CÓ] • {os.path.basename(clean_path)}", "FILE_OLD",
                    )
                continue

            if any(err_kw in lowered for err_kw in (
                "[error]", "error:", "httperror", "401", "404", "unauthorized",
            )):
                self.log(f"   ❌ {stripped}", "LOG_WARN")
                continue

            if "[warning]" in lowered:
                self.log(f"   ⚠️ {stripped}", "LOG_WARN")
                continue

            if not stripped.startswith("#"):
                self.log(f"   ℹ️ {stripped}", "LOG_NORMAL")

        total_files = local_count + new_count
        self.log(
            f"📊 [X Tổng kết]: Đã tải thêm {new_count} tệp mới. "
            f"Tổng số tệp trong thư mục: {total_files} tệp.",
            "LOG_SYSTEM",
        )

    def _normalize_twitter_target(self, target: str) -> str:
        cleaned = (
            target.strip()
            .replace("https://twitter.com/", "")
            .replace("https://x.com/", "")
            .split("?")[0]
            .split("#")[0]
            .strip("/")
        )
        if "/status/" in target:
            if cleaned.startswith("http://") or cleaned.startswith("https://"):
                return cleaned.rstrip("/")
            return f"https://twitter.com/{cleaned}"

        username = [p for p in cleaned.split("/") if p][0] if "/" in cleaned else cleaned
        return f"https://twitter.com/{username}/media"
