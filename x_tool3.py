import os
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import messagebox, filedialog

class TwitterToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Công cụ Tải Ảnh X (Twitter) v2.0 - Du Kích 1 Cookie")
        self.root.geometry("780x860")
        self.root.resizable(False, False)
        self.root.configure(bg="#15202B")
        
        self.current_process = None
        self.stop_requested = False
        self.is_tool_unlocked = False
        self.ui_queue = queue.Queue() # Hàng đợi chống treo GUI
        self.selected_cookie_path = "" 
        
        self.thu_muc_anh = r"E:\gallery-dl\twitter"
        
        # --- TIÊU ĐỀ ---
        lbl_title = tk.Label(root, text="X / TWITTER DOWNLOADER GUI", font=("Arial", 15, "bold"), fg="#1DA1F2", bg="#15202B")
        lbl_title.pack(pady=10)
        
        # --- KHU VỰC NHẬP FILE COOKIE X ---
        frame_cookie = tk.Frame(root, bg="#15202B")
        frame_cookie.pack(pady=5, fill="x", padx=20)
        lbl_cookie = tk.Label(frame_cookie, text="BƯỚC 1: Chọn file Cookies X (.txt) để kích hoạt:", font=("Arial", 9, "bold"), fg="#FFAD1F", bg="#15202B")
        lbl_cookie.pack(anchor="w", padx=15, pady=2)
        
        frame_cookie_row = tk.Frame(frame_cookie, bg="#15202B")
        frame_cookie_row.pack(fill="x", padx=15, pady=2)
        self.lbl_path_display = tk.Label(frame_cookie_row, text="Chưa chọn file Cookie X...", font=("Arial", 9, "italic"), bg="#192734", fg="#FFAD1F", anchor="w", bd=2, relief="sunken", height=2)
        self.lbl_path_display.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_browse_cookie = tk.Button(frame_cookie_row, text="📁 Chọn File Cookie", font=("Arial", 9, "bold"), bg="#FFAD1F", fg="#000000", bd=0, cursor="hand2", width=18, command=self.click_chon_file_cookie)
        self.btn_browse_cookie.pack(side="right", ipady=4)
        
        # --- KHU VỰC CHỌN THƯ MỤC LƯU ---
        frame_folder = tk.Frame(root, bg="#15202B")
        frame_folder.pack(pady=5, fill="x", padx=20)
        lbl_folder = tk.Label(frame_folder, text="BƯỚC 2: Đường dẫn thư mục lưu ảnh X (Twitter):", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#15202B")
        lbl_folder.pack(anchor="w", padx=15)
        
        frame_folder_row = tk.Frame(frame_folder, bg="#15202B")
        frame_folder_row.pack(fill="x", padx=15, pady=2)
        self.lbl_display_folder = tk.Label(frame_folder_row, text=self.thu_muc_anh, font=("Arial", 10, "bold"), bg="#192734", fg="#1DA1F2", anchor="w", bd=2, relief="sunken", height=2)
        self.lbl_display_folder.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_browse_folder = tk.Button(frame_folder_row, text="⚙️ Đổi Thư Mục", font=("Arial", 9, "bold"), bg="#1DA1F2", fg="#FFFFFF", bd=0, cursor="hand2", width=18, command=self.click_chon_thu_muc_luu)
        self.btn_browse_folder.pack(side="right", ipady=4)
        
        # --- KHU VỰC NHẬP LINK PROFILE ---
        frame_input = tk.Frame(root, bg="#15202B")
        frame_input.pack(pady=5, fill="x", padx=20)
        lbl_input = tk.Label(frame_input, text="BƯỚC 3: Paste link/username mới hoặc chọn user local bên dưới:", font=("Arial", 10, "bold"), fg="#FFFFFF", bg="#15202B")
        lbl_input.pack(anchor="w", padx=15, pady=2)
        self.entry_link = tk.Entry(frame_input, font=("Arial", 11), bg="#192734", fg="#FFFFFF", insertbackground="white", bd=2)
        self.entry_link.pack(fill="x", padx=15, ipady=4)

        lbl_user_list = tk.Label(frame_input, text="Danh sách user đã có trên máy (click để điền vào ô trên):", font=("Arial", 9), fg="#8899A6", bg="#15202B")
        lbl_user_list.pack(anchor="w", padx=15, pady=(4, 2))
        frame_user_list = tk.Frame(frame_input, bg="#15202B")
        frame_user_list.pack(fill="x", padx=15, pady=(0, 2))
        scrollbar_users = tk.Scrollbar(frame_user_list, orient="vertical")
        scrollbar_users.pack(side="right", fill="y")
        self.listbox_users = tk.Listbox(
            frame_user_list, font=("Arial", 10), height=6,
            bg="#192734", fg="#FFFFFF", selectbackground="#1DA1F2", selectforeground="#FFFFFF",
            activestyle="none", bd=2, highlightthickness=0,
            yscrollcommand=scrollbar_users.set,
        )
        self.listbox_users.pack(side="left", fill="x", expand=True)
        scrollbar_users.config(command=self.listbox_users.yview)
        self.listbox_users.bind("<<ListboxSelect>>", self.chon_user_tu_danh_sach)

        # --- KHU VỰC NHẬP LINK LIVESTREAM ---
        frame_live = tk.Frame(root, bg="#15202B")
        frame_live.pack(pady=5, fill="x", padx=20)
        lbl_live = tk.Label(frame_live, text="BƯỚC 4: Paste link Livestream đã kết thúc (tweet/broadcast):", font=("Arial", 10, "bold"), fg="#FFFFFF", bg="#15202B")
        lbl_live.pack(anchor="w", padx=15, pady=2)
        frame_live_row = tk.Frame(frame_live, bg="#15202B")
        frame_live_row.pack(fill="x", padx=15, pady=2)
        self.entry_livestream = tk.Entry(frame_live_row, font=("Arial", 11), bg="#192734", fg="#FFFFFF", insertbackground="white", bd=2)
        self.entry_livestream.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=4)
        self.btn4 = tk.Button(frame_live_row, text="[4] TẢI LIVESTREAM", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#9B59B6", state=tk.DISABLED, command=self.click_tai_livestream, width=18, cursor="hand2")
        self.btn4.pack(side="right", ipady=4)
        
        # --- KHU VỰC NÚT BẤM TÍNH NĂNG ---
        frame_buttons = tk.Frame(root, bg="#15202B")
        frame_buttons.pack(pady=10)
        
        self.btn1 = tk.Button(frame_buttons, text="[1] Cập nhật TOÀN BỘ", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#1DA1F2", state=tk.DISABLED, command=self.click_cap_nhat_het, width=20, height=2)
        self.btn1.grid(row=0, column=0, padx=4, pady=5)
        
        self.btn2 = tk.Button(frame_buttons, text="[2] Chỉ cập nhật MỘT acc", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#17BF63", state=tk.DISABLED, command=self.click_cap_nhat_mot, width=20, height=2)
        self.btn2.grid(row=0, column=1, padx=4, pady=5)
        
        self.btn3 = tk.Button(frame_buttons, text="[3] THÊM MỚI tài khoản", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#FFAD1F", state=tk.DISABLED, command=self.click_them_moi, width=20, height=2)
        self.btn3.grid(row=0, column=2, padx=4, pady=5)
        
        self.btn_stop = tk.Button(frame_buttons, text="[STOP] DỪNG LẠI", font=("Arial", 9, "bold"), fg="#FFFFFF", bg="#E0245E", state=tk.DISABLED, command=self.click_dung_lai, width=20, height=2)
        self.btn_stop.grid(row=0, column=3, padx=4, pady=5)
        
        # --- CỬA SỔ LOG ĐEN ---
        lbl_log = tk.Label(root, text="Tiến trình chạy ngầm (Log):", font=("Arial", 9, "bold"), fg="#8899A6", bg="#15202B")
        lbl_log.pack(anchor="w", padx=35)
        self.txt_log = tk.Text(root, bg="#000000", font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.txt_log.pack(fill="both", expand=True, padx=35, pady=(0, 15))
        
        # Định nghĩa màu sắc log giống bản Instagram
        self.txt_log.tag_config("LOG_SYSTEM", foreground="#00FFFF")  
        self.txt_log.tag_config("LOG_WARN", foreground="#FFAD1F")    
        self.txt_log.tag_config("FILE_OLD", foreground="#555555")     
        self.txt_log.tag_config("FILE_NEW", foreground="#00FF00")     
        self.txt_log.tag_config("LOG_NORMAL", foreground="#FFFFFF")   
        
        self.log_print("🔒 HỆ THỐNG ĐANG KHÓA. Hãy bấm nút 'Chọn File Cookie' để kích hoạt công cụ X.\n", "LOG_WARN")
        self.lam_moi_danh_sach_user()
        self.xu_ly_hang_doi_ui()

    def log_print(self, text, tag_name="LOG_NORMAL"):
        self.ui_queue.put(("log", (text, tag_name)))

    def clear_log(self):
        self.ui_queue.put(("clear", None))

    def xu_ly_hang_doi_ui(self):
        try:
            # Giới hạn lấy tối đa 50 event để tránh block UI nếu queue quá dài
            count = 0
            while count < 50:
                action, data = self.ui_queue.get_nowait()
                if action == "log":
                    text, tag_name = data
                    self.txt_log.insert(tk.END, text, tag_name)
                    self.txt_log.see(tk.END)
                elif action == "clear":
                    self.txt_log.delete("1.0", tk.END)
                elif action == "update_label_cookie":
                    path = data
                    self.lbl_path_display.config(text=f" ✔ {path}", fg="#00FF00")
                elif action == "update_label_folder":
                    self.lbl_display_folder.config(text=data)
                elif action == "unlock_system":
                    self.btn1.config(state=tk.NORMAL)
                    self.btn2.config(state=tk.NORMAL)
                    self.btn3.config(state=tk.NORMAL)
                    self.btn4.config(state=tk.NORMAL)
                elif action == "buttons_state":
                    state = data
                    self.btn1.config(state=state)
                    self.btn2.config(state=state)
                    self.btn3.config(state=state)
                    self.btn4.config(state=state)
                    self.btn_browse_cookie.config(state=state)
                    self.btn_browse_folder.config(state=state)
                elif action == "stop_state":
                    self.btn_stop.config(state=data)
                elif action == "refresh_user_list":
                    self._cap_nhat_listbox_user(data)
                elif action == "add_user_list":
                    self._them_user_listbox(data)
                self.ui_queue.task_done()
                count += 1
        except queue.Empty:
            pass
        self.root.after(50, self.xu_ly_hang_doi_ui)

    def click_chon_file_cookie(self):
        file_path = filedialog.askopenfilename(title="Chọn file chứa Twitter/X Cookies", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if file_path:
            self.selected_cookie_path = file_path
            self.ui_queue.put(("update_label_cookie", file_path))
            self.is_tool_unlocked = True
            self.ui_queue.put(("unlock_system", None))
            self.clear_log()
            self.log_print("🔓 Đã MỞ KHÓA: Đã nạp file Cookie X thành công.\n\n", "LOG_SYSTEM")

    def click_chon_thu_muc_luu(self):
        folder_selected = filedialog.askdirectory(title="Chọn thư mục chứa ảnh X (Twitter)")
        if folder_selected:
            self.thu_muc_anh = os.path.normpath(folder_selected)
            self.ui_queue.put(("update_label_folder", self.thu_muc_anh))
            self.log_print(f"📁 Đã đổi thư mục làm việc thành: {self.thu_muc_anh}\n", "LOG_SYSTEM")
            self.lam_moi_danh_sach_user()

    def quet_user_local(self):
        if not os.path.exists(self.thu_muc_anh):
            return []
        return sorted(
            [f for f in os.listdir(self.thu_muc_anh) if os.path.isdir(os.path.join(self.thu_muc_anh, f))],
            key=str.lower,
        )

    def lam_moi_danh_sach_user(self):
        self.ui_queue.put(("refresh_user_list", self.quet_user_local()))

    def _cap_nhat_listbox_user(self, users):
        self.listbox_users.delete(0, tk.END)
        for user in users:
            self.listbox_users.insert(tk.END, user)

    def _them_user_listbox(self, user):
        if not user:
            return
        users = list(self.listbox_users.get(0, tk.END))
        if user not in users:
            users.append(user)
            users.sort(key=str.lower)
        self._cap_nhat_listbox_user(users)
        idx = users.index(user)
        self.listbox_users.selection_clear(0, tk.END)
        self.listbox_users.selection_set(idx)
        self.listbox_users.see(idx)

    def them_user_vao_danh_sach(self, user):
        user = self.chuan_hoa_username(user)
        if user:
            self.ui_queue.put(("add_user_list", user))

    def chon_user_tu_danh_sach(self, event=None):
        sel = self.listbox_users.curselection()
        if not sel:
            return
        user = self.listbox_users.get(sel[0])
        self.entry_link.delete(0, tk.END)
        self.entry_link.insert(0, user)

    def chuan_hoa_username(self, raw):
        if not raw:
            return ""
        s = raw.strip().replace('"', "")
        for prefix in (
            "https://x.com/", "http://x.com/",
            "https://twitter.com/", "http://twitter.com/",
            "https://mobile.twitter.com/", "http://mobile.twitter.com/",
        ):
            if s.lower().startswith(prefix):
                s = s[len(prefix):]
                break
        if "?" in s:
            s = s.split("?")[0]
        if s.endswith("/"):
            s = s[:-1]
        return s.split("/")[0].strip()

    def lay_ten_user(self):
        return self.chuan_hoa_username(self.entry_link.get())

    def _startupinfo_an_cua_so(self):
        if os.name != "nt":
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo

    def lay_user_tu_link_live(self, url):
        url = url.strip().replace('"', "")
        if "?" in url:
            url = url.split("?")[0]
        if url.endswith("/"):
            url = url[:-1]

        for prefix in (
            "https://x.com/", "http://x.com/",
            "https://twitter.com/", "http://twitter.com/",
            "https://mobile.twitter.com/", "http://mobile.twitter.com/",
        ):
            if not url.lower().startswith(prefix):
                continue
            parts = url[len(prefix):].split("/")
            if parts and parts[0] and parts[0] not in ("i", "intent", "search", "home", "explore", "hashtag"):
                return parts[0]
            break

        try:
            # Sửa tham số thành uploader_id để lấy chính xác username thay vì Display Name
            result = subprocess.run(
                ["yt-dlp", "--cookies", self.selected_cookie_path, "--print", "uploader_id", url],
                capture_output=True, text=True, timeout=90,
                startupinfo=self._startupinfo_an_cua_so(), errors="ignore",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().lstrip("@").split()[0]
        except FileNotFoundError:
             self.log_print("❌ Thiếu thư viện yt-dlp. Vui lòng cài đặt yt-dlp.\n", "LOG_WARN")
        except Exception:
            pass
        return ""

    def dem_so_file(self, folder_path):
        if not os.path.exists(folder_path): return 0
        count = 0
        for _, _, files in os.walk(folder_path):
            count += len(files)
        return count

    def run_cmd_thread(self, target_function):
        if not self.is_tool_unlocked: return
        self.stop_requested = False
        self.ui_queue.put(("buttons_state", tk.DISABLED))
        self.ui_queue.put(("stop_state", tk.NORMAL))
        def wrapper():
            try:
                target_function()
            except Exception as e:
                 self.log_print(f"❌ LỖI HỆ THỐNG: {str(e)}\n", "LOG_WARN")
            finally:
                self.root.after(0, self.khoi_phuc_man_hinh_chinh)
        threading.Thread(target=wrapper, daemon=True).start()

    def khoi_phuc_man_hinh_chinh(self):
        if self.is_tool_unlocked: self.ui_queue.put(("buttons_state", tk.NORMAL))
        self.ui_queue.put(("stop_state", tk.DISABLED))
        self.current_process = None

    def thuc_thi_gallery_dl(self, url, dest_folder, chi_quet_bai_moi=False):
        if self.stop_requested: return False

        cmd = [
            "python", "-m", 
            "gallery_dl", url,
            "--destination", dest_folder,
            "--cookies", self.selected_cookie_path, 
            # TĂNG LÊN ĐỂ CHẠY CHẬM, AN TOÀN TRÁNH BỊ X KHÓA ACC
            "--sleep-request", "3-10",
            "--sleep", "1-5",
            "-o", "cache.file=none",
            "-o", 'directory=["."]'
        ]
        
        if chi_quet_bai_moi:
             cmd.extend(["-o", "twitter:tweets=5"])

        try:
            self.current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=False, bufsize=1,
                startupinfo=self._startupinfo_an_cua_so(), errors="ignore",
            )
        except FileNotFoundError:
             self.log_print("❌ Thiếu thư viện gallery-dl! Hãy đảm bảo bạn đã cài đặt gallery-dl.\n", "LOG_WARN")
             return False
        
        count = 0
        bi_rate_limit = False

        for line in self.current_process.stdout:
            if self.stop_requested: break
            strip_line = line.strip()
            
            # Highlight màu sắc log
            if any(kw in strip_line.lower() for kw in [".jpg", ".mp4", ".png", ".webp"]) and not strip_line.startswith("#"):
                count += 1
                self.log_print(f"[NEW DOWNLOAD] -> {strip_line}\n", "FILE_NEW")
            elif strip_line.startswith("#"): 
                self.log_print(f"{strip_line}\n", "FILE_OLD")
            else:
                self.log_print(f"{strip_line}\n", "LOG_NORMAL")
            
            # Phát hiện nếu tài khoản dính giới hạn Rate Limit của X
            if any(err in line.lower() for err in ["429", "rate limit", "too many requests"]):
                bi_rate_limit = True

        self.current_process.wait()

        if bi_rate_limit:
            self.log_print("\n⚠️ [CẢNH BÁO]: Tài khoản X của bạn đã đạt giới hạn tải trong ngày (Rate Limit Exceeded).\n", "LOG_WARN")
            self.log_print("👉 Vui lòng TẮT TOOL và đợi từ 4 - 6 tiếng để X reset băng thông rồi mới chạy tiếp!\n", "LOG_WARN")
            return False

        return True

    def thuc_thi_yt_dlp(self, url, dest_folder):
        if self.stop_requested:
            return False

        output_tpl = os.path.join(dest_folder, "%(title)s [%(id)s].%(ext)s")
        cmd = [
            "yt-dlp", url,
            "--cookies", self.selected_cookie_path,
            "-o", output_tpl,
            "--merge-output-format", "mp4",
            "--no-part",
            "--retries", "5",
            "--fragment-retries", "5",
        ]

        try:
            self.current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=False, bufsize=1,
                startupinfo=self._startupinfo_an_cua_so(), errors="ignore",
            )
        except FileNotFoundError:
             self.log_print("❌ Thiếu thư viện yt-dlp! Hãy đảm bảo bạn đã cài đặt yt-dlp.\n", "LOG_WARN")
             return False

        thanh_cong = False
        for line in self.current_process.stdout:
            if self.stop_requested:
                break
            strip_line = line.strip()
            if not strip_line:
                continue

            lower = strip_line.lower()
            if "destination:" in lower or "downloading" in lower or "merging" in lower or lower.endswith((".mp4", ".m4a", ".ts", ".webm")):
                self.log_print(f"[LIVESTREAM] -> {strip_line}\n", "FILE_NEW")
            elif any(err in lower for err in ["error", "unable", "private", "login"]):
                self.log_print(f"{strip_line}\n", "LOG_WARN")
            else:
                self.log_print(f"{strip_line}\n", "LOG_NORMAL")

            if "has already been downloaded" in lower or "100%" in strip_line:
                thanh_cong = True

        self.current_process.wait()
        return self.current_process.returncode == 0 or thanh_cong

    def click_tai_livestream(self):
        url = self.entry_livestream.get().strip()
        if not url:
            messagebox.showwarning("Thiếu link", "Hãy paste link livestream đã kết thúc vào ô Bước 4.")
            return
        if not url.startswith("http"):
            messagebox.showwarning("Link không hợp lệ", "Link phải bắt đầu bằng http:// hoặc https://")
            return

        self.clear_log()

        def processing():
            user = self.lay_user_tu_link_live(url)
            if not user:
                self.log_print("❌ Không xác định được username từ link. Thử link dạng:\n   https://x.com/username/status/...\n", "LOG_WARN")
                return

            target_path = os.path.join(self.thu_muc_anh, user)
            os.makedirs(target_path, exist_ok=True)
            file_truoc = self.dem_so_file(target_path)

            self.log_print(f"📺 Đang tải livestream của: {user}\n   Link: {url}\n   Lưu tại: {target_path}\n\n", "LOG_SYSTEM")

            thanh_cong = self.thuc_thi_yt_dlp(url, target_path)
            file_sau = self.dem_so_file(target_path)

            if thanh_cong:
                self.them_user_vao_danh_sach(user)
                self.log_print(f"\n📊 [KẾT QUẢ]: Đã tải xong livestream. Thêm {file_sau - file_truoc} file. (Tổng: {file_sau} files)\n", "LOG_SYSTEM")
            else:
                self.log_print("\n⚠️ [CẢNH BÁO]: Tải livestream thất bại hoặc bị dừng giữa chừng.\n", "LOG_WARN")

        self.run_cmd_thread(processing)

    def click_dung_lai(self):
         # Chạy hộp thoại trên luồng riêng để không block main thread
         def xac_nhan_dung():
             if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn DỪNG tiến trình cào X hiện tại?"):
                self.stop_requested = True
                if self.current_process:
                    try:
                        self.current_process.terminate()
                        self.current_process.wait(timeout=3)
                    except Exception:
                        try:
                            self.current_process.kill()
                        except Exception:
                            pass
                self.root.after(0, self.khoi_phuc_man_hinh_chinh)
         threading.Thread(target=xac_nhan_dung, daemon=True).start()

    def click_cap_nhat_het(self):
        self.clear_log()
        def processing():
            if not os.path.exists(self.thu_muc_anh):
                try: os.makedirs(self.thu_muc_anh, exist_ok=True)
                except: return
            subfolders = [f for f in os.listdir(self.thu_muc_anh) if os.path.isdir(os.path.join(self.thu_muc_anh, f))]
            for idx, folder in enumerate(subfolders, 1):
                if self.stop_requested: break
                target_path = os.path.join(self.thu_muc_anh, folder)
                file_truoc = self.dem_so_file(target_path)
                
                self.log_print(f"\n[{idx}/{len(subfolders)}] Đang kiểm tra siêu tốc (5 bài mới) cho: {folder}\n", "LOG_SYSTEM")
                
                thanh_cong = self.thuc_thi_gallery_dl(f"https://x.com/{folder}", target_path, chi_quet_bai_moi=True)
                
                file_sau = self.dem_so_file(target_path)
                self.log_print(f"📊 [KẾT QUẢ - {folder}]: Đã tải thêm {file_sau - file_truoc} files mới. (Tổng: {file_sau} files)\n", "LOG_SYSTEM")
                
                if not thanh_cong: # Nếu dính limit thì dừng luôn cả cụm dọn dẹp
                    break
            self.lam_moi_danh_sach_user()
        self.run_cmd_thread(processing)

    def click_cap_nhat_mot(self):
        user = self.lay_ten_user()
        if not user: 
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập link/username hoặc chọn một user từ danh sách.")
            return
        self.clear_log()
        target_path = os.path.join(self.thu_muc_anh, user)
        def processing():
            file_truoc = self.dem_so_file(target_path)
            self.log_print(f"🚀 Đang kiểm tra 5 bài mới nhất của X: {user}\n   -> Số file hiện tại: {file_truoc}\n\n", "LOG_SYSTEM")
            
            self.thuc_thi_gallery_dl(f"https://x.com/{user}", target_path, chi_quet_bai_moi=True)
            
            file_sau = self.dem_so_file(target_path)
            self.them_user_vao_danh_sach(user)
            self.log_print(f"\n📊 [KẾT QUẢ]: Đã tải thêm {file_sau - file_truoc} files mới. (Tổng: {file_sau} files)\n", "LOG_SYSTEM")
        self.run_cmd_thread(processing)

    def click_them_moi(self):
        user = self.lay_ten_user()
        if not user: 
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập link/username hoặc chọn một user từ danh sách.")
            return
        self.clear_log()
        target_path = os.path.join(self.thu_muc_anh, user)
        def processing():
            os.makedirs(target_path, exist_ok=True)
            self.log_print(f"➕ Thêm mới tài khoản X (Quét toàn bộ kho để lấy hết ảnh cũ): {user}\n", "LOG_SYSTEM")
            
            self.thuc_thi_gallery_dl(f"https://x.com/{user}", target_path, chi_quet_bai_moi=False)
            
            file_sau = self.dem_so_file(target_path)
            self.them_user_vao_danh_sach(user)
            self.log_print(f"\n📊 [KẾT QUẢ]: Hoàn thành! Tổng cộng: {file_sau} files.\n", "LOG_SYSTEM")
        self.run_cmd_thread(processing)

if __name__ == "__main__":
    root = tk.Tk()
    app = TwitterToolGUI(root)
    root.mainloop()