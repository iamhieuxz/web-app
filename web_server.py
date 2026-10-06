"""Universal Downloader Web — FastAPI backend.

File này được tổ chức theo thứ tự sau để tránh NameError:
1. Imports
2. Pydantic models (dùng cho endpoint decorators)
3. Auth helpers
4. Logging setup
5. Shared globals (server_loop, log_manager)
6. Lifespan handler (dùng globals ở trên)
7. app = FastAPI(lifespan=lifespan)  ← KHAI BÁO SỚM NHẤT
8. Static mounts + template setup
9. Route handlers (@app.get, @app.post, ...)
10. uvicorn run
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import threading
import time as _time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

import auth
import database
import utils
from models import AppConfig, RuntimeState, SingleTargetRequest, ListTargetRequest, LiveRequest
from process_manager import ProcessManager
from rate_limit import RateLimitGuard, RateLimitPolicy
from downloader import Downloader
from services import InstagramService, TwitterService


# ==========================================
# 1. PYDANTIC MODELS
# ==========================================
class FileRequest(BaseModel):
    current_path: str = ""
    name: str = ""
    new_name: str = ""


class PathUpdateRequest(BaseModel):
    path: str


class AccountActionRequest(BaseModel):
    username: str
    platform: str | None = None
    is_active: int | None = None


# ==========================================
# 2. AUTH HELPERS
# ==========================================
def _extract_token(
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    token: str | None = Query(default=None),
) -> str | None:
    return x_auth_token or token


def require_auth(provided: str | None = Depends(_extract_token)) -> None:
    if not auth.verify_token(provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid auth token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==========================================
# 3. LOGGING SETUP
# ==========================================
_log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_log_format,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("web_app")


# ==========================================
# 4. SHARED GLOBALS (khai báo sớm, gán sau trong lifespan)
# ==========================================
server_loop: asyncio.AbstractEventLoop | None = None


class WebSocketLogManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: str, tag: str = "LOG_NORMAL", platform: str = "ig"):
        async with self._lock:
            connections = list(self.active_connections)
        dead: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(
                    {"message": message, "tag": tag, "platform": platform}
                )
            except Exception:
                dead.append(connection)
        if dead:
            async with self._lock:
                for c in dead:
                    if c in self.active_connections:
                        self.active_connections.remove(c)


log_manager = WebSocketLogManager()


# ==========================================
# 5. LIFESPAN HANDLER (tham chiếu globals ở trên)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global server_loop
    server_loop = asyncio.get_running_loop()

    # Startup
    logger.info("[START] Server đã khởi động trên http://127.0.0.1:8000")
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    os.makedirs(app_config.download_folder, exist_ok=True)

    try:
        yield
    finally:
        # Shutdown
        logger.info("🛑 Đang shutdown server, dừng các process còn sót...")
        try:
            pm_ig.stop(timeout=1.0)
            pm_x.stop(timeout=1.0)
            ig_executor.shutdown(wait=True, cancel_futures=False)
            x_executor.shutdown(wait=True, cancel_futures=False)
        except Exception:
            logger.exception("Lỗi trong quá trình shutdown")
        logger.info("[START] Shutdown hoàn tất")


# ==========================================
# 6. FASTAPI APP (khai báo trước mọi @app.* decorator)
# ==========================================
app = FastAPI(
    title="Universal Downloader Web",
    lifespan=lifespan,
)

# Mount static files sau khi app được khai báo
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Template context cho auth token injection
TEMPLATE_CONTEXT = {"auth_token": auth.AUTH_TOKEN}


# ==========================================
# 7. RATE LIMITER CHO HTTP ENDPOINTS
# ==========================================
class SimpleRateLimiter:
    def __init__(self, max_per_second: float = 5.0) -> None:
        self._max_per_second = max_per_second
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        min_interval = 1.0 / self._max_per_second
        with self._lock:
            last = self._last_call.get(key, 0.0)
            now = _time.monotonic()
            if now - last < min_interval:
                return False
            self._last_call[key] = now
            return True


_endpoint_limiter = SimpleRateLimiter(max_per_second=3.0)


def _check_endpoint_throttle(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _endpoint_limiter.check(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều yêu cầu, vui lòng thử lại sau giây lát",
        )


# ==========================================
# 8. KHỞI TẠO CẤU HÌNH & TRẠNG THÁI
# ==========================================
utils.cleanup_temp_cookies()
database.init_db()
logger.info("[AUTH] Auth token (8 ky tu dau): %s...", auth.AUTH_TOKEN[:8])

saved_root = database.get_setting("download_folder", "/data/downloads")

COOKIE_DIR = os.path.abspath("data/cookies")
os.makedirs(COOKIE_DIR, exist_ok=True)
COOKIE_MAIN_PATH = os.path.join(COOKIE_DIR, "cookie_main.txt")
COOKIE_SUB_PATH = os.path.join(COOKIE_DIR, "cookie_sub.txt")
COOKIE_X_PATH = os.path.join(COOKIE_DIR, "cookie_x.txt")

app_config = AppConfig(download_folder=saved_root)
state_ig = RuntimeState()
state_x = RuntimeState()

if os.path.exists(COOKIE_MAIN_PATH):
    app_config.cookie_path = COOKIE_MAIN_PATH
    state_ig.is_tool_unlocked = True
if os.path.exists(COOKIE_SUB_PATH):
    app_config.backup_cookie_path = COOKIE_SUB_PATH
if os.path.exists(COOKIE_X_PATH):
    app_config.cookie_x_path = COOKIE_X_PATH
    state_x.is_tool_unlocked = True

pm_ig = ProcessManager()
pm_x = ProcessManager()
downloader_ig = Downloader(pm_ig)
downloader_x = Downloader(pm_x)
rate_limit_guard_ig = RateLimitGuard(RateLimitPolicy())
rate_limit_guard_x = RateLimitGuard(RateLimitPolicy())
ig_executor = ThreadPoolExecutor(max_workers=1)
x_executor = ThreadPoolExecutor(max_workers=1)


# ==========================================
# HELPER: GỬI LOG QUA WEBSOCKET
# ==========================================
def _send_log_ig(message: str, tag: str = "LOG_NORMAL") -> None:
    if server_loop and server_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(
                log_manager.broadcast(message, tag, "ig"), server_loop
            )
        except Exception:
            logger.debug("Không gửi được log tới WS", exc_info=True)


def _send_log_x(message: str, tag: str = "LOG_NORMAL") -> None:
    if server_loop and server_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(
                log_manager.broadcast(message, tag, "x"), server_loop
            )
        except Exception:
            logger.debug("Không gửi được log tới WS", exc_info=True)


ig_service = InstagramService(
    downloader_ig, rate_limit_guard_ig, app_config, state_ig, log_callback=_send_log_ig
)
x_service = TwitterService(
    downloader_x, rate_limit_guard_x, app_config, state_x, log_callback=_send_log_x
)


# ==========================================
# 9. STATIC ROUTES (HTML)
# ==========================================
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context=TEMPLATE_CONTEXT
    )


@app.get("/database-manager")
async def db_manager(request: Request):
    return templates.TemplateResponse(
        request=request, name="db_manager.html", context=TEMPLATE_CONTEXT
    )


@app.get("/api/auth/token")
def get_auth_token() -> dict:
    return {"token": auth.AUTH_TOKEN}


# ==========================================
# 10. WEBSOCKET ENDPOINT
# ==========================================
@app.websocket("/ws/log")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not auth.verify_token(token):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await log_manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json(
                        {"message": "", "tag": "PING", "platform": "system"}
                    )
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await log_manager.disconnect(websocket)


# ==========================================
# 11. MEDIA ENDPOINT
# ==========================================
@app.get("/media/{file_path:path}")
async def get_media_dynamic(file_path: str):
    root = os.path.abspath(app_config.download_folder)
    decoded_subpath = urllib.parse.unquote(file_path)
    full_path = os.path.abspath(os.path.join(root, decoded_subpath))
    if not full_path.startswith(root):
        return Response(content="Truy cập bị từ chối", status_code=403)
    if not os.path.isfile(full_path):
        return Response(content="Không tìm thấy tệp", status_code=404)
    return FileResponse(full_path)


# ==========================================
# 12. API INSTAGRAM
# ==========================================
@app.post("/api/ig/download/single", dependencies=[Depends(require_auth)])
def ig_dl_single(req: SingleTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    state_ig.clear_stop()
    pm_ig.clear_stop()
    ig_executor.submit(ig_service.download_single_new, req.target, req.disable_range)
    return {"status": "started"}


@app.post("/api/ig/update/single", dependencies=[Depends(require_auth)])
def ig_up_single(req: SingleTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    state_ig.clear_stop()
    pm_ig.clear_stop()
    ig_executor.submit(
        ig_service.update_single,
        req.target,
        req.disable_range,
        req.include_posts,
        req.include_stories,
        req.include_highlights,
    )
    return {"status": "started"}


@app.post("/api/ig/download/list", dependencies=[Depends(require_auth)])
def ig_dl_list(req: ListTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    targets = req.targets if req.targets else database.get_active_accounts("instagram")
    if not targets:
        return {"status": "error", "message": "Chưa có tài khoản nào trong danh sách hoặc Database"}
    state_ig.clear_stop()
    pm_ig.clear_stop()
    ig_executor.submit(ig_service.download_list_new, targets, req.disable_range)
    return {"status": "started"}


@app.post("/api/ig/update/list", dependencies=[Depends(require_auth)])
def ig_up_list(req: ListTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    targets = req.targets if req.targets else database.get_active_accounts("instagram")
    if not targets:
        return {"status": "error", "message": "Chưa có tài khoản nào trong danh sách hoặc Database"}
    state_ig.clear_stop()
    pm_ig.clear_stop()
    ig_executor.submit(
        ig_service.update_list,
        targets,
        req.disable_range,
        req.include_posts,
        req.include_stories,
        req.include_highlights,
    )
    return {"status": "started"}


@app.post("/api/ig/sync/local", dependencies=[Depends(require_auth)])
def ig_sync_local(request: Request):
    _check_endpoint_throttle(request)
    state_ig.clear_stop()
    pm_ig.clear_stop()
    ig_executor.submit(ig_service.sync_all_local)
    return {"status": "started"}


@app.post("/api/ig/stop", dependencies=[Depends(require_auth)])
def ig_stop(request: Request):
    _check_endpoint_throttle(request)
    state_ig.request_stop()
    pm_ig.request_stop()
    pm_ig.stop()
    return {"status": "stopped"}


# ==========================================
# 13. API X / TWITTER
# ==========================================
@app.post("/api/x/download/single", dependencies=[Depends(require_auth)])
def x_dl_single(req: SingleTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.download_single, req.target)
    return {"status": "started"}


@app.post("/api/x/update/single", dependencies=[Depends(require_auth)])
def x_up_single(req: SingleTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.update_single, req.target)
    return {"status": "started"}


@app.post("/api/x/download/list", dependencies=[Depends(require_auth)])
def x_dl_list(req: ListTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    targets = req.targets if req.targets else database.get_active_accounts("twitter")
    if not targets:
        return {"status": "error", "message": "Chưa có tài khoản nào trong danh sách hoặc Database"}
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.download_list, targets)
    return {"status": "started"}


@app.post("/api/x/update/list", dependencies=[Depends(require_auth)])
def x_up_list(req: ListTargetRequest, request: Request):
    _check_endpoint_throttle(request)
    targets = req.targets if req.targets else database.get_active_accounts("twitter")
    if not targets:
        return {"status": "error", "message": "Chưa có tài khoản nào trong danh sách hoặc Database"}
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.update_list, targets)
    return {"status": "started"}


@app.post("/api/x/sync/local", dependencies=[Depends(require_auth)])
def x_sync_local(request: Request):
    _check_endpoint_throttle(request)
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.sync_all_local)
    return {"status": "started"}


@app.post("/api/x/livestream", dependencies=[Depends(require_auth)])
def x_livestream(req: LiveRequest, request: Request):
    _check_endpoint_throttle(request)
    state_x.clear_stop()
    pm_x.clear_stop()
    x_executor.submit(x_service.download_livestream, req.target)
    return {"status": "started"}


@app.post("/api/x/stop", dependencies=[Depends(require_auth)])
def x_stop(request: Request):
    _check_endpoint_throttle(request)
    state_x.request_stop()
    pm_x.request_stop()
    pm_x.stop()
    return {"status": "stopped"}


@app.post("/api/stop", dependencies=[Depends(require_auth)])
def api_stop(request: Request):
    _check_endpoint_throttle(request)
    state_ig.request_stop()
    pm_ig.request_stop()
    state_x.request_stop()
    pm_x.request_stop()
    pm_ig.stop()
    pm_x.stop()
    return {"status": "stopped"}


# ==========================================
# 14. API CẤU HÌNH & COOKIE
# ==========================================
MAX_COOKIE_SIZE = 1 * 1024 * 1024  # 1 MB


@app.get("/api/config/status")
def get_config_status():
    return {
        "has_main_cookie": os.path.exists(COOKIE_MAIN_PATH),
        "has_sub_cookie": os.path.exists(COOKIE_SUB_PATH),
        "has_x_cookie": os.path.exists(COOKIE_X_PATH),
        "current_root": app_config.download_folder,
    }


@app.post("/api/config/upload-cookies", dependencies=[Depends(require_auth)])
async def upload_cookies(
    request: Request,
    cookie1: UploadFile | None = File(None),
    cookie2: UploadFile | None = File(None),
    cookieX: UploadFile | None = File(None),
):
    _check_endpoint_throttle(request)

    async def _save(upload: UploadFile, dest: str) -> None:
        size = 0
        with open(dest, "wb") as buffer:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_COOKIE_SIZE:
                    buffer.close()
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Cookie quá lớn (> {MAX_COOKIE_SIZE // 1024} KB)",
                    )
                buffer.write(chunk)

    if cookie1:
        await _save(cookie1, COOKIE_MAIN_PATH)
        app_config.cookie_path = os.path.abspath(COOKIE_MAIN_PATH)
        state_ig.is_tool_unlocked = True
        try:
            subprocess.run(
                ["gallery-dl", "--clear-cache", "instagram"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    if cookie2:
        await _save(cookie2, COOKIE_SUB_PATH)
        app_config.backup_cookie_path = os.path.abspath(COOKIE_SUB_PATH)

    if cookieX:
        await _save(cookieX, COOKIE_X_PATH)
        app_config.cookie_x_path = os.path.abspath(COOKIE_X_PATH)
        state_x.is_tool_unlocked = True
        try:
            subprocess.run(
                ["gallery-dl", "--clear-cache", "twitter"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    return {"status": "success"}


@app.post("/api/config/update-path", dependencies=[Depends(require_auth)])
def api_update_path(req: PathUpdateRequest, request: Request):
    _check_endpoint_throttle(request)
    new_path = (req.path or "").strip()
    if not new_path:
        return {"status": "error", "message": "Đường dẫn không hợp lệ"}
    if not utils.is_safe_download_path(new_path):
        return {
            "status": "error",
            "message": "Đường dẫn không an toàn (nằm trong thư mục hệ thống hoặc không có quyền ghi)",
        }
    try:
        os.makedirs(new_path, exist_ok=True)
    except OSError as e:
        return {"status": "error", "message": f"Không tạo được thư mục: {e}"}
    try:
        database.set_setting("download_folder", new_path)
    except Exception:
        logger.exception("Không lưu được download_folder vào DB")
    app_config.download_folder = new_path
    return {"status": "success", "new_path": new_path}


def ask_windows_folder(initial_dir: str = "") -> str:
    safe_dir = initial_dir.replace("\\", "/") if initial_dir and os.path.exists(initial_dir) else ""
    script = (
        "import sys, os, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "initial = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "root.wm_attributes('-topmost', 1)\n"
        "root.lift()\n"
        "root.focus_force()\n"
        "path = filedialog.askdirectory(title='Chọn thư mục lưu trữ media', initialdir=initial)\n"
        "root.destroy()\n"
        "if path: print(os.path.normpath(path))\n"
    )
    si = None
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script, safe_dir],
            capture_output=True, text=True, startupinfo=si, timeout=120,
        )
        out = proc.stdout.strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        logger.exception("Lỗi khi mở folder picker")
    return ""


@app.get("/api/config/browse-folder")
def browse_folder():
    path = ask_windows_folder(app_config.download_folder)
    if path:
        return {"status": "success", "path": path}
    return {"status": "cancelled"}


# ==========================================
# 15. API DATABASE ACCOUNTS
# ==========================================
@app.get("/api/db/accounts")
def api_get_db_accounts():
    accounts = database.get_all_accounts()
    return accounts if isinstance(accounts, list) else []


@app.post("/api/db/accounts/add", dependencies=[Depends(require_auth)])
def api_add_db_account(req: AccountActionRequest, request: Request):
    _check_endpoint_throttle(request)
    username = utils.clean_username(req.username or "")
    platform = (req.platform or "instagram").lower()
    if platform not in ("instagram", "twitter"):
        return {"status": "error", "message": "Platform không hợp lệ"}
    if not username:
        return {"status": "error", "message": "Username không hợp lệ hoặc chứa ký tự cấm"}
    if database.add_account(username, platform):
        return {"status": "success"}
    return {"status": "error", "message": "Không thể thêm tài khoản"}


@app.post("/api/db/accounts/toggle", dependencies=[Depends(require_auth)])
def api_toggle_db_account(req: AccountActionRequest, request: Request):
    _check_endpoint_throttle(request)
    username = req.username or ""
    if not utils.is_valid_username(username):
        return {"status": "error", "message": "Username không hợp lệ"}
    is_active = 1 if req.is_active else 0
    try:
        database.toggle_account_status(username, is_active)
        return {"status": "success"}
    except Exception:
        logger.exception("Lỗi toggle_account")
        return {"status": "error", "message": "Lỗi DB"}


@app.post("/api/db/accounts/delete", dependencies=[Depends(require_auth)])
def api_delete_db_account(req: AccountActionRequest, request: Request):
    _check_endpoint_throttle(request)
    username = req.username or ""
    if not utils.is_valid_username(username):
        return {"status": "error", "message": "Username không hợp lệ"}
    try:
        database.delete_account(username)
        return {"status": "success"}
    except Exception:
        logger.exception("Lỗi delete_account")
        return {"status": "error", "message": "Lỗi DB"}


# ==========================================
# 16. API STORAGE
# ==========================================
_STORAGE_MAX_DEPTH = 5


@app.post("/api/storage/open-local", dependencies=[Depends(require_auth)])
def open_local_item(req: FileRequest, request: Request):
    _check_endpoint_throttle(request)
    root = app_config.download_folder
    target = os.path.join(root, req.current_path, req.name) if req.name else os.path.join(root, req.current_path)
    norm_target = os.path.normpath(target)
    norm_root = os.path.normpath(root)
    if not norm_target.startswith(norm_root):
        return {"status": "error", "message": "Truy cập bị từ chối (path traversal)"}
    if not os.path.exists(norm_target):
        return {"status": "error", "message": "Tệp hoặc thư mục không tồn tại"}
    try:
        if sys.platform == "win32":
            if os.path.isdir(norm_target):
                os.startfile(norm_target)
            else:
                subprocess.Popen(["explorer", f"/select,{norm_target}"], shell=False)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/storage/stats")
def get_storage_stats():
    root = app_config.download_folder
    norm_root = os.path.normpath(root)
    if not os.path.exists(norm_root):
        return {"error": "Thư mục chưa tồn tại"}

    total_size, total_files = 0, 0
    folder_stats: list[dict] = []
    ext_stats = {"Image (JPG/PNG)": 0, "Video (MP4)": 0, "Khác": 0}
    ig_user_count, twitter_user_count = 0, 0

    try:
        entries = os.listdir(norm_root)
    except OSError as e:
        return {"error": f"Không đọc được thư mục: {e}"}

    # === PHASE 1: Dem folders va user count (khong bi anh huong boi truncated) ===
    all_folders_info = []
    for folder in entries:
        folder_path = os.path.join(norm_root, folder)
        if not os.path.isdir(folder_path):
            continue
        try:
            max_mtime = os.path.getmtime(folder_path)
        except OSError:
            max_mtime = 0

        # Dem subfolders (accounts)
        if folder.lower() == "instagram":
            try:
                ig_user_count = sum(1 for s in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, s)))
            except OSError:
                ig_user_count = 0
        elif folder.lower() == "twitter":
            try:
                twitter_user_count = sum(1 for s in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, s)) and s != "Livestreams_X")
            except OSError:
                twitter_user_count = 0
        
        all_folders_info.append({"name": folder, "folder_path": folder_path, "mtime": max_mtime, "size": 0, "count": 0})

    # === PHASE 2: Xu ly files ===
    for f_info in all_folders_info:
        folder = f_info["name"]
        folder_path = f_info["folder_path"]
        f_size, f_count, max_mtime = f_info["mtime"], 0, f_info["mtime"]
        
        for root_dir, dirs, files in os.walk(folder_path):
            depth = root_dir[len(folder_path):].count(os.sep)
            if depth >= _STORAGE_MAX_DEPTH:
                dirs[:] = []
                continue
            for file in files:
                f_count += 1
                total_files += 1
                ext = os.path.splitext(file)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".webp"):
                    ext_stats["Image (JPG/PNG)"] += 1
                elif ext in (".mp4", ".mov", ".ts", ".m3u8"):
                    ext_stats["Video (MP4)"] += 1
                else:
                    ext_stats["Khác"] += 1
                try:
                    file_path = os.path.join(root_dir, file)
                    s = os.path.getsize(file_path)
                    fmtime = os.path.getmtime(file_path)
                    f_size += s
                    total_size += s
                    if fmtime > max_mtime:
                        max_mtime = fmtime
                except OSError:
                    pass
        
        # Luon append folder_stats sau khi xu ly xong folder
        folder_stats.append({
            "name": folder,
            "size_mb": round(f_size / (1024 * 1024), 2),
            "count": f_count,
            "is_dir": True,
            "mtime": max_mtime,
        })

    folder_stats.sort(key=lambda x: x["mtime"], reverse=True)
    return {
        "root_path": norm_root,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "total_files": total_files,
        "total_folders": len(folder_stats),
        "ig_user_count": ig_user_count,
        "twitter_user_count": twitter_user_count,
        "ext_stats": ext_stats,
        "all_folders": folder_stats,
    }


@app.post("/api/storage/explore", dependencies=[Depends(require_auth)])
def explore_storage(req: FileRequest, request: Request):
    _check_endpoint_throttle(request)
    root = os.path.normpath(app_config.download_folder)
    target_dir = os.path.normpath(os.path.join(root, req.current_path)) if req.current_path else root
    if not target_dir.startswith(root) or not os.path.exists(target_dir):
        return {"error": "Invalid path"}
    items = []
    try:
        names = os.listdir(target_dir)
    except OSError as e:
        return {"error": f"Không đọc được thư mục: {e}"}
    for name in names:
        full_path = os.path.join(target_dir, name)
        is_dir = os.path.isdir(full_path)
        size, mtime = 0, 0
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            pass
        if not is_dir:
            try:
                size = os.path.getsize(full_path)
            except OSError:
                pass
        items.append({
            "name": name,
            "is_dir": is_dir,
            "size_mb": round(size / (1024 * 1024), 2),
            "count": "-",
            "mtime": mtime,
        })
    items.sort(key=lambda x: (not x["is_dir"], -x["mtime"]))
    return {"items": items}


@app.post("/api/storage/rename", dependencies=[Depends(require_auth)])
def rename_item(req: FileRequest, request: Request):
    _check_endpoint_throttle(request)
    root = os.path.normpath(app_config.download_folder)
    base_dir = os.path.normpath(os.path.join(root, req.current_path))
    old_path = os.path.normpath(os.path.join(base_dir, req.name))
    new_path = os.path.normpath(os.path.join(base_dir, req.new_name))
    if not old_path.startswith(root) or not new_path.startswith(root):
        return {"status": "error", "message": "Lỗi bảo mật (path traversal)"}
    if not req.new_name or not utils.is_valid_filename(req.new_name):
        return {"status": "error", "message": "Tên mới không hợp lệ"}
    if os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            os.rename(old_path, new_path)
            return {"status": "success"}
        except OSError as e:
            return {"status": "error", "message": f"Không đổi tên được: {e}"}
    return {"status": "error", "message": "Tên mới đã tồn tại hoặc tệp cũ không tồn tại"}


@app.post("/api/storage/delete", dependencies=[Depends(require_auth)])
def delete_item(req: FileRequest, request: Request):
    _check_endpoint_throttle(request)
    root = os.path.normpath(app_config.download_folder)
    base_dir = os.path.normpath(os.path.join(root, req.current_path)) if req.current_path else root
    if not base_dir.startswith(root):
        return {"status": "error", "message": "Lỗi bảo mật (path traversal)"}
    target = os.path.normpath(os.path.join(base_dir, req.name))
    if not target.startswith(root):
        return {"status": "error", "message": "Lỗi bảo mật (path traversal)"}
    try:
        if not os.path.exists(target):
            return {"status": "error", "message": "Không tìm thấy tệp/thư mục"}
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return {"status": "success"}
    except OSError as e:
        return {"status": "error", "message": str(e)}


# ==========================================
# 17. KHỞI ĐỘNG SERVER
# ==========================================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8000))
    logger.info("Starting Web Server on 0.0.0.0:%d", PORT)
    logger.info("Auth token: %s", auth.AUTH_TOKEN[:8])
    try:
        uvicorn.run(
            "web_server:app",
            host="0.0.0.0",
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        logger.info("Server interrupted")
