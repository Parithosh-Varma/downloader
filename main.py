import os
import sys
import subprocess
import tempfile
import shutil
import json
from flask import Flask, render_template, request, send_file, jsonify

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


def format_duration(seconds):
    if not seconds:
        return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_media_info(url):
    result = subprocess.run(
        ytdlp_cmd() + ["--no-download", "--dump-json", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise Exception(result.stderr.strip())

    data = json.loads(result.stdout)
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
            height = f.get("height") or ""
            label = f"{height}p" if height else f.get("format_note", "")
            if f.get("ext"):
                label += f" {f['ext'].upper()}"
            video_formats.append({
                "format_id": f["format_id"],
                "label": label.strip(),
                "ext": f.get("ext", ""),
                "filesize": size_str,
                "has_audio": has_audio,
            })
        elif has_audio and not has_video:
            abr = f.get("abr") or ""
            label = f"{int(abr)}kbps" if abr else f.get("format_note", "")
            if f.get("ext"):
                label += f" {f['ext'].upper()}"
            audio_formats.append({
                "format_id": f["format_id"],
                "label": label.strip(),
                "ext": f.get("ext", ""),
                "filesize": size_str,
            })

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
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "Please enter a URL"}), 400
    try:
        info = fetch_media_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    url = request.json.get("url", "").strip()
    format_id = request.json.get("format_id", "")
    mode = request.json.get("mode", "video")

    if not url or not format_id:
        return jsonify({"error": "Missing parameters"}), 400

    tmpdir = tempfile.mkdtemp()
    try:
        output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
        cmd = ytdlp_cmd() + [
            "-f", format_id,
            "-o", output_template,
            "--no-playlist",
            "--print", "filename",
            url,
        ]
        if mode == "audio":
            cmd.extend(["-x", "--audio-format", "mp3"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return jsonify({"error": result.stderr.strip()}), 500

        filename = result.stdout.strip().split("\n")[-1]
        if not os.path.exists(filename):
            for f in os.listdir(tmpdir):
                filename = os.path.join(tmpdir, f)
                break

        return send_file(filename, as_attachment=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
