/**
 * Database Manager - Account Management Module
 * Handles storage browsing, file operations, and database account CRUD
 */

// ============================================================
// Global State
// ============================================================
let currentItems = [];
let currentPath = "";
let typeChartInstance = null;
let topChartInstance = null;
let allDbAccounts = [];

const AUTH_TOKEN = window.AUTH_TOKEN || "";

// ============================================================
// Authentication Helper
// ============================================================
function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (AUTH_TOKEN) {
        options.headers["X-Auth-Token"] = AUTH_TOKEN;
    }
    return fetch(url, options).then(res => {
        if (res.status === 401) {
            alert("🔒 Phiên đã hết hạn. Vui lòng tải lại trang (F5).");
            throw new Error("Unauthorized");
        }
        if (res.status === 429) {
            alert("⏳ Quá nhiều yêu cầu, thử lại sau.");
            throw new Error("Rate limited");
        }
        return res;
    });
}

// ============================================================
// Storage Browser - Main View
// ============================================================
async function loadCurrentView() {
    renderBreadcrumbs();
    
    const overlay = document.getElementById("loadingOverlay");
    overlay.classList.remove("hidden");
    overlay.classList.add("flex");

    try {
        if (currentPath === "") {
            // Root view: show stats, charts, and DB accounts
            document.getElementById("statsSection").classList.remove("hidden");
            
            const [resStats, resDb, resConfig] = await Promise.all([
                authFetch('/api/storage/stats'),
                authFetch('/api/db/accounts'),
                authFetch('/api/config/status')
            ]);
            
            const data = await resStats.json();
            const dbAccounts = await resDb.json();
            const configStatus = await resConfig.json();
            
            if(data.error) throw new Error(data.error);

            // Update stats display
            document.getElementById("rootPathDisplay").textContent = `Đường dẫn gốc: ${data.root_path}`;
            document.getElementById("rootPathInput").value = configStatus.current_root || data.root_path;
            
            document.getElementById("statSize").textContent = `${data.total_size_mb} MB`;
            document.getElementById("statFiles").textContent = data.total_files.toLocaleString();
            document.getElementById("statIgUsers").textContent = (data.ig_user_count || 0).toLocaleString();
            document.getElementById("statXUsers").textContent = (data.twitter_user_count || 0).toLocaleString();

            // Draw charts and store data
            drawCharts(data.ext_stats, data.all_folders);
            currentItems = data.all_folders;
            
            // Load DB accounts for search
            allDbAccounts = Array.isArray(dbAccounts) ? dbAccounts : [];
            filterDbAccounts();
        } else {
            // Subdirectory view
            document.getElementById("statsSection").classList.add("hidden");
            const res = await authFetch('/api/storage/explore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_path: currentPath })
            });
            const data = await res.json();
            if(data.error) throw new Error(data.error);
            currentItems = data.items;
        }
        renderTable();
    } catch (error) {
        console.error("Lỗi load view:", error);
        if (error.message === "Unauthorized" || error.message === "Rate limited") return;
        alert("Lỗi: " + error.message);
        if (currentPath !== "")) { 
            currentPath = ""; 
            loadCurrentView(); 
        }
    } finally {
        overlay.classList.remove("flex");
        overlay.classList.add("hidden");
    }
}

// ============================================================
// Path Configuration
// ============================================================
async function openFolderBrowser() {
    const btn = document.getElementById("browseBtn");
    const originalText = btn.innerHTML;
    btn.innerHTML = "<span>⏳ Đang mở hộp thoại...</span>";
    btn.disabled = true;

    try {
        const res = await authFetch('/api/config/browse-folder');
        const data = await res.json();
        if (data.status === "success" && data.path) {
            document.getElementById("rootPathInput").value = data.path;
            await updateRootPath();
        }
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        alert("Lỗi kết nối tới máy chủ.");
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function updateRootPath() {
    const newPath = document.getElementById("rootPathInput").value.trim();
    if (!newPath) return alert("Vui lòng nhập đường dẫn hợp lệ!");

    try {
        const res = await authFetch('/api/config/update-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: newPath })
        });
        const data = await res.json();
        if (data.status === "success") {
            alert("Đã cập nhật đường dẫn gốc thành công!");
            loadCurrentView();
        } else {
            alert("Lỗi: " + data.message);
        }
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        alert("Lỗi kết nối tới máy chủ.");
    }
}

// ============================================================
// Local File Operations
// ============================================================
async function openInLocalExplorer(itemName = "") {
    try {
        await authFetch('/api/storage/open-local', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_path: currentPath, name: itemName })
        });
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        console.error("Không thể mở trên Windows:", e);
    }
}

// ============================================================
// Database Account Search
// ============================================================
/**
 * Filter and display database accounts based on search query
 */
function filterDbAccounts() {
    const searchInput = document.getElementById("dbSearchInput");
    const clearBtn = document.getElementById("clearSearchBtn");
    const query = (searchInput?.value || "").toLowerCase().trim();

    if (clearBtn) {
        clearBtn.classList.toggle("hidden", query.length === 0);
    }

    if (!query) {
        renderDbAccountsTable(allDbAccounts);
        return;
    }

    const filtered = allDbAccounts.filter(acc => 
        (acc.username && acc.username.toLowerCase().includes(query)) ||
        (acc.platform && acc.platform.toLowerCase().includes(query))
    );

    renderDbAccountsTable(filtered, query);
}

function clearDbSearch() {
    const searchInput = document.getElementById("dbSearchInput");
    if (searchInput) {
        searchInput.value = "";
        filterDbAccounts();
        searchInput.focus();
    }
}

// ============================================================
// Utility Functions
// ============================================================
function escapeHtml(text) {
    if (text == null) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function escapeRegex(str) {
    return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ============================================================
// Database Accounts Table
// ============================================================
function renderDbAccountsTable(accounts, searchQuery = "") {
    const tbody = document.getElementById("dbAccountsBody");
    const badge = document.getElementById("accountCountBadge");
    if (!tbody) return;

    if (badge) {
        badge.textContent = `${accounts.length}/${allDbAccounts.length} accounts`;
    }
    
    tbody.innerHTML = "";
    
    if (!Array.isArray(accounts) || accounts.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 4;
        td.className = "text-center py-6 text-zinc-500 italic";
        if (searchQuery) {
            const safeQ = escapeHtml(searchQuery);
            td.innerHTML = `Không tìm thấy tài khoản nào khớp với từ khóa "<strong>${safeQ}</strong>".`;
        } else {
            td.textContent = "Chưa có tài khoản nào trong Database.";
        }
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    const safeQ = (searchQuery || "").toLowerCase();
    const frag = document.createDocumentFragment();
    
    accounts.forEach(acc => {
        const isInstagram = acc.platform === 'instagram';
        const badgeColor = isInstagram ? 'bg-pink-900/40 text-pink-300 border-pink-700' : 'bg-blue-900/40 text-blue-300 border-blue-700';
        const isActive = acc.is_active === 1;
        const safeUsername = escapeHtml(acc.username || "");

        const tr = document.createElement("tr");
        tr.className = "hover:bg-zinc-700/30 transition-colors";

        // Column 1: Platform badge
        const td1 = document.createElement("td");
        td1.className = "px-4 py-3";
        const badge = document.createElement("span");
        badge.className = `text-xs px-2.5 py-1 rounded-full border font-bold ${badgeColor}`;
        badge.textContent = isInstagram ? 'Instagram' : 'X / Twitter';
        td1.appendChild(badge);
        tr.appendChild(td1);

        // Column 2: Username with search highlight
        const td2 = document.createElement("td");
        td2.className = "px-4 py-3 font-bold text-sky-300 font-mono";
        if (safeQ && acc.username && acc.username.toLowerCase().includes(safeQ)) {
            try {
                const re = new RegExp(`(${escapeRegex(searchQuery)})`, "gi");
                const html = `@${safeUsername.replace(re, '<span class="bg-amber-500/30 text-amber-300 px-0.5 rounded">$1</span>')}`;
                td2.innerHTML = html;
            } catch (e) {
                td2.textContent = `@${safeUsername}`;
            }
        } else {
            td2.textContent = `@${safeUsername}`;
        }
        tr.appendChild(td2);

        // Column 3: Active toggle
        const td3 = document.createElement("td");
        td3.className = "px-4 py-3";
        const label = document.createElement("label");
        label.className = "relative inline-flex items-center cursor-pointer";
        
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = !!isActive;
        input.className = "sr-only peer";
        input.addEventListener("change", () => toggleDbAccount(acc.username, input.checked));
        
        const slider = document.createElement("div");
        slider.className = "w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600";
        
        const statusSpan = document.createElement("span");
        statusSpan.className = "ml-2 text-xs text-zinc-400 font-bold";
        statusSpan.textContent = isActive ? 'Đang bật' : 'Đã tắt';
        
        label.appendChild(input);
        label.appendChild(slider);
        label.appendChild(statusSpan);
        td3.appendChild(label);
        tr.appendChild(td3);

        // Column 4: Delete button
        const td4 = document.createElement("td");
        td4.className = "px-4 py-3 text-right";
        const delBtn = document.createElement("button");
        delBtn.className = "bg-red-900/50 border border-red-800 hover:bg-red-600 text-red-200 hover:text-white text-xs px-3 py-1 rounded transition-colors font-bold shadow";
        delBtn.textContent = "Xóa";
        delBtn.addEventListener("click", () => deleteDbAccount(acc.username));
        td4.appendChild(delBtn);
        tr.appendChild(td4);

        frag.appendChild(tr);
    });
    
    tbody.appendChild(frag);
}

async function toggleDbAccount(username, isActive) {
    // Optimistic update
    const acc = allDbAccounts.find(a => a.username === username);
    if (acc) acc.is_active = isActive ? 1 : 0;

    try {
        await authFetch('/api/db/accounts/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, is_active: isActive ? 1 : 0 })
        });
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        console.error("Lỗi toggle:", e);
    }
}

async function deleteDbAccount(username) {
    if (!confirm(`Xóa vĩnh viễn tài khoản @${username} khỏi Database?`)) return;
    
    // Remove from local cache immediately
    allDbAccounts = allDbAccounts.filter(a => a.username !== username);
    filterDbAccounts();

    try {
        await authFetch('/api/db/accounts/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        console.error("Lỗi delete:", e);
    }
}

// ============================================================
// File Browser Navigation
// ============================================================
function renderBreadcrumbs() {
    const container = document.getElementById("breadcrumb");
    if (!container) return;
    container.innerHTML = "";

    const openRootBtn = document.createElement("button");
    openRootBtn.title = "Mở thư mục này trên Windows";
    openRootBtn.className = "ml-2 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white px-2 py-0.5 rounded border border-zinc-700 transition";
    openRootBtn.textContent = "📂 Mở trên máy";
    openRootBtn.addEventListener("click", () => openInLocalExplorer(''));

    if (currentPath === "") {
        const home = document.createElement("span");
        home.className = "text-sky-400 font-bold";
        home.textContent = "🏠 Root (Thư mục gốc)";
        container.appendChild(home);
        container.appendChild(openRootBtn);
        return;
    }

    // Home button
    const home = document.createElement("button");
    home.className = "hover:text-sky-400 text-zinc-400 transition font-bold";
    home.textContent = "🏠 Root";
    home.addEventListener("click", () => navigateTo(''));
    container.appendChild(home);

    // Path segments
    const parts = currentPath.split('/');
    let builtPath = "";
    parts.forEach((part, index) => {
        builtPath += (builtPath === "" ? "" : "/") + part;
        
        const sep = document.createElement("span");
        sep.className = "text-zinc-600 font-bold mx-1";
        sep.textContent = "/";
        container.appendChild(sep);
        
        if (index === parts.length - 1) {
            const last = document.createElement("span");
            last.className = "text-sky-400 font-bold";
            last.textContent = part;
            container.appendChild(last);
        } else {
            const seg = document.createElement("button");
            seg.className = "hover:text-sky-400 text-zinc-400 transition";
            seg.textContent = part;
            seg.addEventListener("click", () => navigateTo(builtPath));
            container.appendChild(seg);
        }
    });
    
    container.appendChild(openRootBtn);
}

function navigateTo(path) { 
    currentPath = path; 
    loadCurrentView(); 
}

// ============================================================
// File/Folder Table Rendering
// ============================================================
function renderTable() {
    const tbody = document.getElementById("folderTableBody");
    if (!tbody) return;
    
    const sortMode = document.getElementById("sortSelect")?.value || 'mtime';
    let sorted = [...currentItems];
    
    // Sort by selected mode
    if (sortMode === 'size') {
        sorted.sort((a, b) => b.size_mb - a.size_mb);
    } else if (sortMode === 'mtime') {
        sorted.sort((a, b) => b.mtime - a.mtime);
    } else if (sortMode === 'name') {
        sorted.sort((a, b) => a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : (a.is_dir ? -1 : 1));
    }

    tbody.innerHTML = "";
    if (sorted.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 4;
        td.className = "text-center py-6 text-zinc-500 italic";
        td.textContent = "Thư mục trống";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    const frag = document.createDocumentFragment();
    
    sorted.forEach(f => {
        const icon = f.is_dir ? "📁" : "📄";
        const safeName = f.name || "";
        const targetPath = currentPath ? currentPath + '/' + safeName : safeName;

        const tr = document.createElement("tr");
        tr.className = "hover:bg-zinc-700/30 transition-colors";

        // Column 1: Name (clickable)
        const td1 = document.createElement("td");
        td1.className = "px-5 py-4";
        
        if (f.is_dir) {
            const btn = document.createElement("button");
            btn.className = "text-sky-400 hover:text-pink-400 font-bold transition-colors text-left";
            btn.textContent = `${icon} ${safeName}`;
            btn.addEventListener("click", () => navigateTo(targetPath));
            td1.appendChild(btn);
            
            if (currentPath === "") {
                const meta = document.createElement("span");
                meta.className = "ml-2 text-xs text-zinc-500 font-mono";
                meta.textContent = `(${f.count} files)`;
                td1.appendChild(meta);
            }
        } else {
            const a = document.createElement("a");
            a.href = `/media/${encodeURIComponent(targetPath)}`;
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            a.className = "text-emerald-400 hover:text-pink-400 font-bold transition-colors";
            a.textContent = `${icon} ${safeName}`;
            td1.appendChild(a);
        }
        tr.appendChild(td1);

        // Column 2: Size
        const td2 = document.createElement("td");
        td2.className = "px-5 py-4 text-zinc-400 font-mono text-xs";
        td2.textContent = f.size_mb > 0 ? `${f.size_mb} MB` : '-';
        tr.appendChild(td2);

        // Column 3: Modified time
        const td3 = document.createElement("td");
        td3.className = "px-5 py-4 text-zinc-400 font-mono text-xs";
        td3.textContent = f.mtime
            ? new Date(f.mtime * 1000).toLocaleString('vi-VN', { 
                day: '2-digit', month: '2-digit', year: 'numeric', 
                hour: '2-digit', minute: '2-digit' 
              })
            : '-';
        tr.appendChild(td3);

        // Column 4: Actions
        const td4 = document.createElement("td");
        td4.className = "px-5 py-4 text-right space-x-2";
        
        // Open in Explorer button
        const btnOpen = document.createElement("button");
        btnOpen.title = "Mở vị trí tệp trên máy tính";
        btnOpen.className = "bg-zinc-700 hover:bg-zinc-500 text-white text-xs px-2.5 py-1.5 rounded transition-colors font-bold shadow";
        btnOpen.textContent = "📂 Xem trên máy";
        btnOpen.addEventListener("click", () => openInLocalExplorer(safeName));
        td4.appendChild(btnOpen);

        // Rename button
        const btnRename = document.createElement("button");
        btnRename.className = "bg-zinc-700 hover:bg-zinc-500 text-white text-xs px-2.5 py-1.5 rounded transition-colors font-bold shadow";
        btnRename.textContent = "Sửa tên";
        btnRename.addEventListener("click", () => promptRename(safeName));
        td4.appendChild(btnRename);

        // Delete button
        const btnDel = document.createElement("button");
        btnDel.className = "bg-red-900/50 border border-red-800 hover:bg-red-600 text-red-200 hover:text-white text-xs px-2.5 py-1.5 rounded transition-colors font-bold shadow";
        btnDel.textContent = "Xóa";
        btnDel.addEventListener("click", () => promptDelete(safeName));
        td4.appendChild(btnDel);

        tr.appendChild(td4);
        frag.appendChild(tr);
    });
    
    tbody.appendChild(frag);
}

// ============================================================
// File Operations
// ============================================================
async function promptRename(oldName) {
    const newName = prompt(`Nhập tên mới cho "${oldName}":`, oldName);
    if (!newName || newName === oldName) return;
    
    document.getElementById("loadingOverlay").classList.replace("hidden", "flex");
    try {
        const res = await authFetch('/api/storage/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_path: currentPath, name: oldName, new_name: newName })
        });
        if ((await res.json()).status === "success") {
            await loadCurrentView();
        } else {
            alert("Lỗi đổi tên!");
        }
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        alert("Lỗi đổi tên: " + e.message);
    } finally {
        document.getElementById("loadingOverlay").classList.replace("flex", "hidden");
    }
}

async function promptDelete(name) {
    if (!confirm(`⚠️ Bạn có chắc muốn XÓA VĨNH VIỄN "${name}" không?`)) return;
    
    document.getElementById("loadingOverlay").classList.replace("hidden", "flex");
    try {
        const res = await authFetch('/api/storage/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_path: currentPath, name: name })
        });
        if ((await res.json()).status === "success") {
            await loadCurrentView();
        } else {
            alert("Lỗi xóa!");
        }
    } catch (e) {
        if (e.message === "Unauthorized" || e.message === "Rate limited") return;
        alert("Lỗi xóa: " + e.message);
    } finally {
        document.getElementById("loadingOverlay").classList.replace("flex", "hidden");
    }
}

// ============================================================
// Charts
// ============================================================
function drawCharts(extStats, folders) {
    Chart.defaults.color = '#a1a1aa';
    Chart.defaults.font.family = 'Segoe UI, sans-serif';
    
    // Type distribution doughnut chart
    const ctxType = document.getElementById('typeChart').getContext('2d');
    if(typeChartInstance) typeChartInstance.destroy();
    typeChartInstance = new Chart(ctxType, {
        type: 'doughnut',
        data: {
            labels: Object.keys(extStats),
            datasets: [{
                data: Object.values(extStats),
                backgroundColor: ['#ec4899', '#3b82f6', '#f59e0b'],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            },
            cutout: '65%'
        }
    });
    
    // Top 5 folders bar chart
    const top5 = folders.slice(0, 5);
    const ctxTop = document.getElementById('topFoldersChart').getContext('2d');
    if(topChartInstance) topChartInstance.destroy();
    topChartInstance = new Chart(ctxTop, {
        type: 'bar',
        data: {
            labels: top5.map(f => f.name),
            datasets: [{
                label: 'Số lượng tệp',
                data: top5.map(f => f.count),
                backgroundColor: '#10b981',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { grid: { color: '#3f3f46' } },
                x: { grid: { display: false } }
            }
        }
    });
}

// ============================================================
// Initialization
// ============================================================
window.onload = loadCurrentView;
