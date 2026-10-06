from __future__ import annotations

import ctypes
import os
import re
import sys
import glob
import tempfile
from pathlib import Path

# Whitelist pattern cho username IG / Twitter / X: chỉ chấp nhận chữ cái, số, dấu chấm, gạch dưới, gạch ngang
# Độ dài 1-30 ký tự theo giới hạn thực tế của 2 nền tảng
_USERNAME_PATTERN = re.compile(r"^(?!\.)(?!.*\.\.)(?!.*\.$)[A-Za-z0-9._-]{1,30}$")


def is_admin() -> bool:
    try:
        import sys
        if sys.platform != "win32":
            return False
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin_privileges() -> None:
    if is_admin():
        return
    import sys
    if sys.platform == "win32":
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()


def is_valid_username(username: str) -> bool:
    """Kiểm tra username có hợp lệ và an toàn không (chống path traversal, XSS qua DB)."""
    if not username or not isinstance(username, str):
        return False
    return bool(_USERNAME_PATTERN.match(username))


def clean_username(raw_input: str) -> str:
    if not raw_input:
        return ""
    s = raw_input.strip().replace('"', '')
    s = s.replace("https://instagram.com/", "").replace("https://www.instagram.com/", "")
    if "/" in s:
        s = s.split("/")[0]
    if "?" in s:
        s = s.split("?")[0]
    s = s.strip()
    # Áp dụng whitelist để loại bỏ ký tự nguy hiểm còn sót (chống XSS / path traversal)
    return s if is_valid_username(s) else ""


# Backward-compatible alias
def sanitize_username(raw_input: str) -> str:
    return clean_username(raw_input)


def count_local_files(folder_path: str) -> int:
    path = Path(folder_path)
    if not path.exists():
        return 0
    return sum(1 for entry in path.rglob("*") if entry.is_file())


# ==========================================
# PATH VALIDATION
# ==========================================
# Danh sách đen các thư mục hệ thống nhạy cảm không cho phép dùng làm download root
# trên Windows. Mục đích: chống vô tình walk/đọc toàn bộ ổ C khi user nhập nhầm.
_FORBIDDEN_PATH_FRAGMENTS = (
    os.path.normpath("C:/Windows"),
    os.path.normpath("C:/Windows/System32"),
    os.path.normpath("C:/Program Files"),
    os.path.normpath("C:/Program Files (x86)"),
    os.path.normpath("C:/ProgramData"),
)


def is_safe_download_path(path_str: str) -> bool:
    """Kiểm tra đường dẫn có an toàn để làm root download không.

    Trả về False nếu:
    - Path rỗng hoặc chứa null byte
    - Path nằm trong các thư mục hệ thống bị cấm (Windows, Program Files...)
    - Path không có quyền ghi (chỉ check khi đã tồn tại)
    """
    if not path_str or not isinstance(path_str, str):
        return False
    if "\x00" in path_str:
        return False

    try:
        norm = os.path.normpath(path_str)
        # So với các path bị cấm
        for forbidden in _FORBIDDEN_PATH_FRAGMENTS:
            if norm.lower() == forbidden.lower() or norm.lower().startswith(forbidden.lower() + os.sep):
                return False
    except Exception:
        return False

    # Nếu đã tồn tại, check có quyền ghi không
    if os.path.exists(norm):
        return os.access(norm, os.W_OK)

    # Chưa tồn tại, kiểm tra cha có quyền tạo không
    parent = os.path.dirname(norm) or "."
    return os.access(parent, os.W_OK) if os.path.exists(parent) else True


# Ký tự cấm trong tên file Windows
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_valid_filename(name: str) -> bool:
    """Kiểm tra tên file/folder có hợp lệ trên Windows không."""
    if not name or not isinstance(name, str):
        return False
    if len(name) > 255:
        return False
    if name in (".", "..", "CON", "PRN", "AUX", "NUL") or _INVALID_FILENAME_CHARS.search(name):
        return False
    # Không được kết thúc bằng dấu cách hoặc dấu chấm
    if name.endswith(" ") or name.endswith("."):
        return False
    return True


def cleanup_temp_cookies() -> None:
    """[CẢI TIẾN] Dọn dẹp các file cookie tạm bị sót lại do ứng dụng crash từ các phiên trước."""
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, 'ig_cookie_*.txt')
    count = 0
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            count += 1
        except Exception:
            pass
    if count > 0:
        print(f"[CLEANUP] Đã dọn dẹp {count} file cookie tạm (rác) từ phiên làm việc trước.")