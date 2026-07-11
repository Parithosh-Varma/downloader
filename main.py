import os
import sys
import subprocess
import tempfile
import shutil
import json
import re
import logging
from flask import Flask, render_template, request, send_file, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


def ytdlp_cmd():
    candidates = [
        shutil.which("yt-dlp"),
        shutil.which("yt-dlp", path=os.path.expanduser("~/.local/bin")),
    ]
    for c in candidates:
        if c:
            return [c]
    return [sys.executable, "-m", "yt_dlp"]


def is_youtube(url):
    return re.search(r"(youtube\.com|youtu\.be)", url)


def video_sort_key(f):
    return -f.get("height", 0)


def write_cookie_file(cookies_text):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write("# Netscape HTTP Cookie File\n")
    tmp.write(cookies_text)
    tmp.close()
    return tmp.name


def safe_remove(path):
    try:
        os.remove(path)
    except Exception:
        pass


def build_ytdlp_args(url, cookie_file=None):
    args = []
    if cookie_file and os.path.exists(cookie_file):
        args += ["--cookies", cookie_file]
    return args


def format_duration(seconds):
    if not seconds:
        return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_media_info(url, cookie_file=None):
    result = subprocess.run(
        ytdlp_cmd() + build_ytdlp_args(url, cookie_file) + ["--no-download", "--dump-json", "--no-warnings", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        raise Exception(msg[:500])

    start = result.stdout.find("{")
    data = json.loads(result.stdout[start:]) if start != -1 else json.loads(result.stdout)
    title = data.get("title", "Unknown")
    author = data.get("uploader") or data.get("creator") or data.get("channel", "")
    thumbnail = data.get("thumbnail", "")
    duration = format_duration(data.get("duration"))

    video_formats = []
    audio_formats = []

    for f in data.get("formats", []):
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        has_video = vcodec != "none"
        has_audio = acodec != "none"
        if not has_video and not has_audio:
            continue

        filesize = f.get("filesize") or f.get("filesize_approx")
        size_str = ""
        if filesize:
            size_mb = filesize / 1048576
            size_str = f"{size_mb:.1f} MB"

        if has_video:
            height = f.get("height") or 0
            label = f"{height}p" if height else f.get("format_note", "")
            if f.get("ext"):
                label += f" {f['ext'].upper()}"
            video_formats.append({
                "format_id": f["format_id"],
                "label": label.strip(),
                "ext": f.get("ext", ""),
                "filesize": size_str,
                "height": height,
                "has_audio": has_audio,
            })
        elif has_audio and not has_video:
            abr = f.get("abr") or 0
            label = f"{int(abr)}kbps" if abr else f.get("format_note", "")
            if f.get("ext"):
                label += f" {f['ext'].upper()}"
            audio_formats.append({
                "format_id": f["format_id"],
                "label": label.strip(),
                "ext": f.get("ext", ""),
                "filesize": size_str,
                "abr": abr,
            })

    video_formats.sort(key=video_sort_key)
    audio_formats.sort(key=lambda f: -f.get("abr", 0))

    best_video = {"format_id": "bestvideo+bestaudio/best", "label": "Best (auto)", "ext": "mp4", "filesize": "", "height": 99999, "has_audio": True}
    best_audio = {"format_id": "bestaudio/best", "label": "Best (auto)", "ext": "mp3", "filesize": "", "abr": 99999}
    video_formats.insert(0, best_video)
    audio_formats.insert(0, best_audio)

    return {
        "title": title,
        "author": author,
        "thumbnail": thumbnail,
        "duration": duration,
        "video_formats": video_formats,
        "audio_formats": audio_formats,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    cookies = body.get("cookies", "").strip()
    if not url:
        return jsonify({"error": "Please enter a URL"}), 400
    cookie_file = None
    if cookies:
        cookie_file = write_cookie_file(cookies)
    try:
        info = fetch_media_info(url, cookie_file)
        return jsonify(info)
    except Exception as e:
        logger.error("fetch failed for %s: %s", url, str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        if cookie_file:
            safe_remove(cookie_file)


@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    format_id = body.get("format_id", "")
    mode = body.get("mode", "video")
    cookies = body.get("cookies", "").strip()

    if not url or not format_id:
        return jsonify({"error": "Missing parameters"}), 400

    cookie_file = None
    if cookies:
        cookie_file = write_cookie_file(cookies)

    tmpdir = tempfile.mkdtemp()
    try:
        output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
        cmd = ytdlp_cmd() + build_ytdlp_args(url, cookie_file) + [
            "-f", format_id,
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
            url,
        ]
        if mode == "audio":
            cmd.extend(["-x", "--audio-format", "mp3"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return jsonify({"error": result.stderr.strip() or result.stdout.strip()}), 500

        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
        if not files:
            return jsonify({"error": "No file produced"}), 500

        return send_file(files[0], as_attachment=True)
    finally:
        if cookie_file:
            safe_remove(cookie_file)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
