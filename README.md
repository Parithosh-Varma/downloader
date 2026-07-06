# DownloaderPro

A self-hosted media downloader powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp). Paste a link, pick a format, download. Supports YouTube, SoundCloud, Vimeo, Twitch, Bandcamp, and hundreds more sites.

## Features

- **Audio & Video** — Download as MP4 (up to 4K) or extract MP3 audio
- **Format picker** — See all available resolutions/bitrates before downloading
- **Dark UI** — Clean, responsive interface that works on desktop and mobile
- **Self-hosted** — Deploy on Railway, Fly.io, or any server

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Open http://localhost:5000 in your browser.

## Deploy on Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

1. Fork or push this repo to GitHub
2. Go to [Railway](https://railway.app) → New Project → Deploy from GitHub repo
3. Railway auto-detects Python — no extra config needed
4. Your app is live in under a minute

## API

### `POST /api/fetch`

Fetch available formats for a URL.

```json
{ "url": "https://youtube.com/watch?v=..." }
```

Returns metadata (title, author, thumbnail, duration) plus lists of video and audio formats with sizes.

### `POST /api/download`

Download a specific format.

```json
{ "url": "...", "format_id": "22", "mode": "video" }
```

Streams the file as an attachment.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT`   | `5000`  | HTTP server port |

## Tech Stack

- **Python** / **Flask** — web framework
- **yt-dlp** — media extraction engine
- **gunicorn** — production WSGI server
- **Tailwind CSS** / **FontAwesome** — UI
