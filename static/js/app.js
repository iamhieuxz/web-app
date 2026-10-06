/**
 * Universal Downloader Web - Main Application
 * Handles UI interactions, WebSocket logging, and API communication
 */

// ============================================================
// DOM Elements & Global State
// ============================================================
const terminalIg = document.getElementById("terminal-ig");
const terminalX = document.getElementById("terminal-x");
const AUTH_TOKEN = window.AUTH_TOKEN || "";

// ============================================================
// Authentication Helper
// ============================================================
/**
 * Fetch wrapper that automatically includes auth token
 * Handles common HTTP errors (401, 429) with user-friendly messages
 */
function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (AUTH_TOKEN) {
        options.headers["X-Auth-Token"] = AUTH_TOKEN;
    }
    
    return fetch(url, options).then(res => {
        if (res.status === 401) {
            addLog("🔒 Phiên làm việc đã hết hạn. Tải lại trang (F5).", "LOG_WARN", "ig");
            addLog("🔒 Phiên làm việc đã hết hạn. Tải lại trang (F5).", "LOG_WARN", "x");
            throw new Error("Unauthorized");
        }
        if (res.status === 429) {
            addLog("⏳ Quá nhiều yêu cầu, thử lại sau giây lát.", "LOG_WARN", "ig");
            addLog("⏳ Quá nhiều yêu cầu, thử lại sau giây lát.", "LOG_WARN", "x");
            throw new Error("Rate limited");
        }
        return res;
    });
}

// ============================================================
// WebSocket Connection
// ============================================================
const ws = new WebSocket(`wss://${window.location.host}/ws/log?token=${encodeURIComponent(AUTH_TOKEN)}`);

const colorMap = {
    'LOG_SYSTEM': 'text-sky-400',
    'LOG_WARN': 'text-amber-400',
    'FILE_OLD': 'text-zinc-500',
    'FILE_NEW': 'text-emerald-400',
    'LOG_NORMAL': 'text-zinc-100'
};

let activeTermTab = 'ig';
let currentPlatform = 'ig';
const VALID_TAGS = new Set(['LOG_SYSTEM', 'LOG_WARN', 'FILE_OLD', 'FILE_NEW', 'LOG_NORMAL']);

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    addLog(data.message, data.tag, data.platform || 'ig');
};

ws.onerror = function() {
    addLog("⚠️ Mất kết nối tới Server. Hãy tải lại trang (F5).", "LOG_WARN", "ig");
    addLog("⚠️ Mất kết nối tới Server. Hãy tải lại trang (F5).", "LOG_WARN", "x");
};

// ============================================================
// Logging Functions
// ============================================================
/**
 * Add a log message to the terminal display
 * @param {string} message - Log message content
 * @param {string} tag - Log type (LOG_SYSTEM, LOG_WARN, FILE_OLD, FILE_NEW, LOG_NORMAL)
 * @param {string} platform - Target platform ('ig' or 'x')
 */
function addLog(message, tag = "LOG_NORMAL", platform = "ig") {
    const targetTerm = platform === 'x' ? terminalX : terminalIg;
    if (!targetTerm) return;

    const safeTag = VALID_TAGS.has(tag) ? tag : 'LOG_NORMAL';

    const span = document.createElement("span");
    span.className = `block ${colorMap[safeTag] || colorMap['LOG_NORMAL']} mb-1`;
    span.textContent = String(message ?? "");
    targetTerm.appendChild(span);
    
    // Auto-scroll to bottom if viewing this platform's log
    if (activeTermTab === platform) {
        targetTerm.scrollTop = targetTerm.scrollHeight;
    } else {
        // Show badge to indicate new logs
        const badge = document.getElementById(`badge-${platform}`);
        if (badge) badge.classList.remove('hidden');
    }
}

// ============================================================
// Tab Switching Functions
// ============================================================
function switchTermTab(platform) {
    activeTermTab = platform;
    const btnIg = document.getElementById('termTabBtn-ig');
    const btnX = document.getElementById('termTabBtn-x');

    if (platform === 'ig') {
        btnIg.className = "px-3 py-1 rounded text-xs font-bold transition flex items-center space-x-1.5 bg-pink-600 text-white shadow";
        btnX.className = "px-3 py-1 rounded text-xs font-bold transition flex items-center space-x-1.5 bg-zinc-900 text-zinc-400 hover:text-white";
        terminalIg.classList.remove('hidden');
        terminalX.classList.add('hidden');
        terminalIg.scrollTop = terminalIg.scrollHeight;
        document.getElementById('badge-ig').classList.add('hidden');
    } else {
        btnX.className = "px-3 py-1 rounded text-xs font-bold transition flex items-center space-x-1.5 bg-blue-600 text-white shadow";
        btnIg.className = "px-3 py-1 rounded text-xs font-bold transition flex items-center space-x-1.5 bg-zinc-900 text-zinc-400 hover:text-white";
        terminalX.classList.remove('hidden');
        terminalIg.classList.add('hidden');
        terminalX.scrollTop = terminalX.scrollHeight;
        document.getElementById('badge-x').classList.add('hidden');
    }
}

function switchTab(platform) {
    currentPlatform = platform;
    const btnIg = document.getElementById('tabBtn-ig');
    const btnX = document.getElementById('tabBtn-x');
    const contentIg = document.getElementById('tabContent-ig');
    const contentX = document.getElementById('tabContent-x');
    const headerTitle = document.getElementById('headerTitle');

    if (platform === 'ig') {
        btnIg.className = "flex-1 py-2 rounded-md font-bold text-sm transition-all bg-pink-600 text-white shadow";
        btnX.className = "flex-1 py-2 rounded-md font-bold text-sm transition-all bg-transparent text-zinc-400 hover:text-white";
        contentIg.classList.remove('hidden');
        contentX.classList.add('hidden');
        headerTitle.textContent = "IG Downloader";
        headerTitle.className = "text-pink-500";
    } else {
        btnX.className = "flex-1 py-2 rounded-md font-bold text-sm transition-all bg-blue-600 text-white shadow";
        btnIg.className = "flex-1 py-2 rounded-md font-bold text-sm transition-all bg-transparent text-zinc-400 hover:text-white";
        contentX.classList.remove('hidden');
        contentIg.classList.add('hidden');
        headerTitle.textContent = "X Downloader";
        headerTitle.className = "text-blue-500";
    }
    switchTermTab(platform);
}

// ============================================================
// Cookie Management
// ============================================================
/**
 * Auto-upload cookie file when user selects it
 * @param {string} platform - Target platform ('ig' or 'x')
 * @param {number} cookieNum - Cookie slot number (1 or 2)
 * @param {HTMLElement} inputElement - File input element
 */
async function handleCookieSelect(platform, cookieNum, inputElement) {
    if (!inputElement.files || inputElement.files.length === 0) return;
    
    const file = inputElement.files[0];
    const formData = new FormData();
    
    if (platform === 'ig') {
        if (cookieNum === 1) formData.append("cookie1", file);
        else formData.append("cookie2", file);
    } else {
        formData.append("cookieX", file);
    }

    const labelId = platform === 'ig' 
        ? (cookieNum === 1 ? 'labelCookie1' : 'labelCookie2') 
        : 'labelCookieX';
    const labelEl = document.getElementById(labelId);
    
    if (labelEl) {
        labelEl.textContent = `⏳ Đang nạp ${file.name}...`;
        labelEl.className = "text-sm text-amber-400 w-2/3 truncate font-bold";
    }

    try {
        const res = await authFetch('/api/config/upload-cookies', { method: 'POST', body: formData });
        if (res.ok) {
            await checkConfigStatus();
            addLog(`✅ Đã nạp thành công Cookie ${platform.toUpperCase()}: ${file.name}`, "FILE_NEW", platform);
        }
    } catch(e) {
        if (labelEl) labelEl.textContent = `❌ Lỗi nạp ${file.name}`;
    }
}

/**
 * Save cookies pasted from iPhone/Android
 * @param {string} platform - Target platform
 * @param {number} cookieNum - Cookie slot number
 */
async function savePastedCookie(platform, cookieNum) {
    const textarea = document.getElementById('pasteCookie-' + platform);
    if (!textarea || !textarea.value.trim()) {
        alert('Vui lòng dán nội dung cookies trước!');
        return;
    }
    
    const blob = new Blob([textarea.value.trim()], { type: 'text/plain' });
    const filename = `pasted_cookie_${Date.now()}.txt`;
    const file = new File([blob], filename, { type: 'text/plain' });
    
    const formData = new FormData();
    if (platform === 'ig') {
        formData.append(cookieNum === 1 ? "cookie1" : "cookie2", file);
    } else {
        formData.append("cookieX", file);
    }
    
    try {
        const res = await authFetch('/api/config/upload-cookies', { method: 'POST', body: formData });
        if (res.ok) {
            await checkConfigStatus();
            addLog(`✅ Đã lưu Cookie ${platform.toUpperCase()} #${cookieNum} từ paste!`, "FILE_NEW", platform);
            textarea.value = '';
        }
    } catch(e) {
        alert('Lỗi khi lưu cookies!');
    }
}

/**
 * Check and update cookie configuration status
 */
async function checkConfigStatus() {
    try {
        const res = await authFetch('/api/config/status');
        const status = await res.json();
        
        if (status.has_main_cookie) {
            document.getElementById("labelCookie1").textContent = "✅ Đang dùng Cookie lưu trong hệ thống.";
            document.getElementById("labelCookie1").className = "text-sm text-emerald-400 w-2/3 truncate font-bold";
        }
        if (status.has_sub_cookie) {
            document.getElementById("labelCookie2").textContent = "✅ Đang dùng Cookie phụ lưu trong hệ thống.";
            document.getElementById("labelCookie2").className = "text-sm text-sky-400 w-2/3 truncate font-bold";
        }
        if (status.has_x_cookie) {
            document.getElementById("labelCookieX").textContent = "✅ Đang dùng Cookie X trong hệ thống.";
            document.getElementById("labelCookieX").className = "text-sm text-blue-400 w-2/3 truncate font-bold";
        }
    } catch(e) { 
        console.error("Chưa kết nối được Server."); 
    }
}

// ============================================================
// Input Mode Switching
// ============================================================
function toggleMode(platform) {
    const mode = document.querySelector(`input[name="mode${platform === 'ig' ? 'Ig' : 'X'}"]:checked`).value;
    document.getElementById(`singleInputBox-${platform}`).classList.toggle('hidden', mode !== 'single');
    document.getElementById(`listInputBox-${platform}`).classList.toggle('hidden', mode !== 'list');
    document.getElementById(`dbInputBox-${platform}`).classList.toggle('hidden', mode !== 'db');
    saveInputState(platform);
}

/**
 * Load list of targets from a .txt file
 */
function loadListFromFile(event, targetTextareaId, platform) {
    const file = event.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        const textarea = document.getElementById(targetTextareaId);
        const currentVal = textarea.value.trim();
        const newVal = e.target.result.trim();
        textarea.value = currentVal ? currentVal + '\n' + newVal : newVal;
        saveInputState(platform);
    };
    reader.readAsText(file);
    event.target.value = ""; 
}

// ============================================================
// LocalStorage Persistence
// ============================================================
/**
 * Save current input state to LocalStorage to prevent data loss on F5
 */
function saveInputState(platform) {
    const modeEl = document.querySelector(`input[name="mode${platform === 'ig' ? 'Ig' : 'X'}"]:checked`);
    if (!modeEl) return;
    const mode = modeEl.value;
    localStorage.setItem(`mode_${platform}`, mode);
    
    if (platform === 'ig') {
        localStorage.setItem("single_ig", document.getElementById("singleTarget-ig").value);
        localStorage.setItem("list_ig", document.getElementById("listTargets-ig").value);
        localStorage.setItem("chk_post", document.getElementById("chkPost").checked);
        localStorage.setItem("chk_story", document.getElementById("chkStory").checked);
        localStorage.setItem("chk_hl", document.getElementById("chkHighlight").checked);
        localStorage.setItem("chk_range", document.getElementById("chkDisableRange").checked);
    } else {
        localStorage.setItem("single_x", document.getElementById("singleTarget-x").value);
        localStorage.setItem("list_x", document.getElementById("listTargets-x").value);
        localStorage.setItem("live_x", document.getElementById("liveTarget-x").value);
    }
}

/**
 * Restore input state from LocalStorage on page load
 */
function restoreInputState() {
    ['ig', 'x'].forEach(platform => {
        const savedMode = localStorage.getItem(`mode_${platform}`);
        if (savedMode) {
            const radio = document.querySelector(`input[name="mode${platform === 'ig' ? 'Ig' : 'X'}"][value="${savedMode}"]`);
            if (radio) { radio.checked = true; toggleMode(platform); }
        }
    });

    if (localStorage.getItem("single_ig")) document.getElementById("singleTarget-ig").value = localStorage.getItem("single_ig");
    if (localStorage.getItem("list_ig")) document.getElementById("listTargets-ig").value = localStorage.getItem("list_ig");
    if (localStorage.getItem("single_x")) document.getElementById("singleTarget-x").value = localStorage.getItem("single_x");
    if (localStorage.getItem("list_x")) document.getElementById("listTargets-x").value = localStorage.getItem("list_x");
    if (localStorage.getItem("live_x")) document.getElementById("liveTarget-x").value = localStorage.getItem("live_x");

    if (localStorage.getItem("chk_post") !== null) document.getElementById("chkPost").checked = localStorage.getItem("chk_post") === "true";
    if (localStorage.getItem("chk_story") !== null) document.getElementById("chkStory").checked = localStorage.getItem("chk_story") === "true";
    if (localStorage.getItem("chk_hl") !== null) document.getElementById("chkHighlight").checked = localStorage.getItem("chk_hl") === "true";
    if (localStorage.getItem("chk_range") !== null) document.getElementById("chkDisableRange").checked = localStorage.getItem("chk_range") === "true";
}

// ============================================================
// Database Account Counts
// ============================================================
/**
 * Update the account count displayed on Database radio buttons
 */
async function updateDbCounts() {
    try {
        const res = await authFetch('/api/db/accounts');
        const accounts = await res.json();
        if (Array.isArray(accounts)) {
            const igCount = accounts.filter(a => 
                (a.platform === 'instagram' || a.platform === 1) && 
                (a.is_active === 1 || a.is_active === '1' || a.is_active == null)
            ).length;
            const xCount = accounts.filter(a => 
                (a.platform === 'twitter' || a.platform === 2) && 
                (a.is_active === 1 || a.is_active === '1' || a.is_active == null)
            ).length;
            document.getElementById("countDb-ig").textContent = igCount;
            document.getElementById("countDb-x").textContent = xCount;
        }
    } catch(e) { console.error("Lỗi đếm DB accounts:", e); }
}

// ============================================================
// Job Execution
// ============================================================
/**
 * Execute download/update job for specified platform
 * @param {string} platform - Target platform ('ig' or 'x')
 * @param {string} action - Job type ('new', 'update', 'sync_all', 'livestream')
 */
async function runJob(platform, action) {
    const targetTerm = platform === 'x' ? terminalX : terminalIg;
    targetTerm.innerHTML = "";
    switchTermTab(platform);
    addLog(`⏳ Đang khởi động Engine ${platform.toUpperCase()}...`, "LOG_SYSTEM", platform);

    // Special handling for livestream
    if (action === 'livestream') {
        const liveTarget = document.getElementById("liveTarget-x").value.trim();
        if (!liveTarget) {
            addLog("⚠️ Lỗi: Bạn chưa nhập link Livestream!", "LOG_WARN", platform);
            return;
        }
        await authFetch("/api/x/livestream", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: liveTarget })
        });
        return;
    }

    // Sync all accounts from database
    if (action === 'sync_all') {
        await authFetch(`/api/${platform}/sync/local`, { method: 'POST' });
        return;
    }

    const mode = document.querySelector(`input[name="mode${platform === 'ig' ? 'Ig' : 'X'}]:checked`).value;
    const payload = {
        disable_range: platform === 'ig' ? document.getElementById("chkDisableRange").checked : true,
        include_posts: platform === 'ig' ? document.getElementById("chkPost").checked : true,
        include_stories: platform === 'ig' ? document.getElementById("chkStory").checked : false,
        include_highlights: platform === 'ig' ? document.getElementById("chkHighlight").checked : false,
        targets: []
    };

    let endpoint = "";

    // Mode 1: Use Database
    if (mode === 'db') {
        endpoint = action === 'new' ? `/api/${platform}/download/list` : `/api/${platform}/update/list`;
        payload.targets = [];
        addLog(`🗄️ Đang lấy danh sách tài khoản từ Database...`, "LOG_SYSTEM", platform);
    } 
    // Mode 2: Single Target
    else if (mode === 'single') {
        const singleVal = document.getElementById(`singleTarget-${platform}`).value.trim();
        if (!singleVal) {
            if (action === 'update') {
                addLog("ℹ️ Ô nhập liệu trống. Hệ thống tự động chuyển sang cập nhật tài khoản từ Database!", "LOG_WARN", platform);
                endpoint = `/api/${platform}/update/list`;
                payload.targets = [];
            } else {
                addLog("⚠️ Lỗi: Bạn chưa nhập Username hoặc URL!", "LOG_WARN", platform);
                return;
            }
        } else {
            payload.target = singleVal;
            endpoint = action === 'new' ? `/api/${platform}/download/single` : `/api/${platform}/update/single`;
        }
    } 
    // Mode 3: List of Targets
    else {
        const rawList = document.getElementById(`listTargets-${platform}`).value;
        const targets = rawList.split('\n').map(s => s.trim()).filter(s => s !== "");
        if (targets.length === 0) {
            if (action === 'update') {
                addLog("ℹ️ Danh sách trống. Hệ thống tự động cập nhật tài khoản từ Database!", "LOG_WARN", platform);
                endpoint = `/api/${platform}/update/list`;
                payload.targets = [];
            } else {
                addLog("⚠️ Lỗi: Danh sách mục tiêu đang trống!", "LOG_WARN", platform);
                return;
            }
        } else {
            payload.targets = targets;
            endpoint = action === 'new' ? `/api/${platform}/download/list` : `/api/${platform}/update/list`;
        }
    }

    try {
        const res = await authFetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === "error") {
            addLog(`⚠️ ${data.message || "Lỗi xử lý yêu cầu"}`, "LOG_WARN", platform);
        }
    } catch(e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        addLog(`⚠️ Lỗi kết nối tới Server: ${e.message}`, "LOG_WARN", platform);
    }
}

/**
 * Stop running job for specified platform
 */
async function runStop(platform) {
    addLog(`🛑 Đang gửi lệnh dừng cho ${platform.toUpperCase()}...`, "LOG_WARN", platform);
    try { 
        await authFetch(`/api/${platform}/stop`, { method: 'POST' }); 
    } catch(e) { 
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        addLog(`⚠️ Không thể gửi lệnh dừng.`, "LOG_WARN", platform); 
    }
}

// ============================================================
// Initialization
// ============================================================
window.onload = async function() {
    await checkConfigStatus();
    await updateDbCounts();
    restoreInputState();
};
