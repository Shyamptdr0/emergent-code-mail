# MailTrack — Gmail Email Tracking Extension + Dashboard

A Mailsuite/Mailtrack-style email tracking tool built on React + FastAPI + MongoDB + Chrome Extension (Manifest V3).

## Features
- Gray tick → Green tick status inside Gmail (sent vs opened)
- Real-time desktop notifications the instant your email is opened
- Custom follow-up scheduler (manual reminder or auto-send mode)
- Web dashboard with stats, tracked email timeline, follow-up manager
- Google OAuth login (Emergent-managed)

## Project structure
```
/app
├── backend/          FastAPI + MongoDB (tracking pixel, auth, follow-ups, SSE)
│   ├── server.py
│   ├── requirements.txt
│   └── .env          (set MONGO_URL, DB_NAME, CORS_ORIGINS)
├── frontend/         React dashboard (Cabinet Grotesk + IBM Plex Sans UI)
│   ├── src/pages/    Landing, Login, Dashboard, Emails, EmailDetail, FollowUps, Settings
│   └── src/lib/      api.js, AuthContext.jsx
└── extension/        Chrome Extension (Manifest V3)
    ├── manifest.json
    ├── background.js content.js popup.html/js
```

## Local setup

### 1. Backend
```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# set backend/.env
# MONGO_URL=mongodb://localhost:27017
# DB_NAME=mailtrack
# CORS_ORIGINS=http://localhost:3000
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend
```bash
cd frontend
yarn install
# set frontend/.env
# REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

### 3. Chrome Extension
1. Open `chrome://extensions` → toggle **Developer mode**
2. **Load unpacked** → select `/app/extension` folder
3. Click the MailTrack icon, paste your Backend URL + API key (from dashboard → Settings)

## Deployment
- Frontend: build with `yarn build` and host on Vercel/Netlify
- Backend: deploy FastAPI on Railway/Render; set env vars
- Extension: package with `zip -r extension.zip extension/` and submit to Chrome Web Store

## License
MIT
