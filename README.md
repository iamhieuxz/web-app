# 📸 Universal Downloader Web

Web interface for downloading media from **Instagram** and **X (Twitter)** using `gallery-dl`.

## ✨ Features

- **Multi-Platform**: Download from Instagram (posts, stories, highlights) and X/Twitter
- **Cookie-Based Auth**: Secure cookie-based authentication (no password needed)
- **Database Management**: Track accounts and sync locally
- **Real-time Logs**: WebSocket-powered live download progress
- **PWA Support**: Install as desktop/mobile app
- **Responsive UI**: Clean dark theme with Tailwind CSS

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Cookies

Create cookie files in `data/cookies/`:
- `cookie_main.txt` - Primary Instagram cookie
- `cookie_sub.txt` - Backup Instagram cookie  
- `cookie_x.txt` - X/Twitter cookie

Or use the **Upload** button in the web UI.

### 3. Run

```bash
python web_server.py
```

Open `http://localhost:5000` in your browser.

## 📁 Project Structure

```
├── web_server.py          # Flask backend server
├── templates/
│   ├── index.html         # Main downloader page
│   └── db_manager.html    # Database management page
├── static/
│   ├── js/
│   │   ├── app.js         # Main UI logic
│   │   └── db_manager.js # DB management logic
│   ├── icons/             # PWA icons
│   ├── manifest.json      # PWA manifest
│   └── sw.js              # Service worker
├── data/
│   └── cookies/           # Cookie storage (gitignored)
└── requirements.txt
```

## ⚙️ Configuration

### Environment Variables (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `5000` |
| `AUTH_TOKEN` | Auth token for sessions | Auto-generated |
| `ROOT_PATH` | Media storage root | `./downloads` |

### Cookie Format

Export cookies from browser as **Netscape format**:

```
# Netscape HTTP Cookie File
.domain.com	TRUE	/	TRUE	0	sessionid	abc123
```

## 🔧 API Endpoints

### Download

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ig/download/single` | Download single IG profile |
| POST | `/api/ig/download/list` | Download multiple IG profiles |
| POST | `/api/ig/update/single` | Update single IG profile |
| POST | `/api/ig/update/list` | Update multiple IG profiles |
| POST | `/api/x/download/single` | Download single X profile |
| POST | `/api/x/download/list` | Download multiple X profiles |

### Database

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/db/accounts` | List all accounts |
| POST | `/api/db/accounts/toggle` | Toggle account active state |
| POST | `/api/db/accounts/delete` | Delete account |

### Storage

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/storage/stats` | Get storage statistics |
| POST | `/api/storage/explore` | Browse storage directory |
| POST | `/api/storage/delete` | Delete file/folder |
| POST | `/api/storage/rename` | Rename file/folder |

## ⚠️ Known Limitations

- **Instagram Highlights**: May not work due to API changes
- **Private Accounts**: Requires valid cookies with access
- **Rate Limiting**: Instagram/X may rate-limit requests

## 📝 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Pull requests welcome! Please read contributing guidelines first.
