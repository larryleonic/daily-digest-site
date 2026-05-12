"""
Vercel Serverless Function: POST /api/feedback
接收用户反馈，通过 GitHub API 追加到仓库的 data/feedback.jsonl
"""

import json
import os
import base64
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from datetime import datetime


# 从 Vercel 环境变量读取
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "larryleonic/daily-digest-site")
FEEDBACK_FILE = "data/feedback.jsonl"


def github_api(method: str, endpoint: str, data: dict = None) -> dict:
    """调用 GitHub API"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "DailyDigest/1.0",
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def append_feedback(feedback: dict) -> bool:
    """追加一条反馈到 GitHub 仓库的 feedback.jsonl"""
    if not GITHUB_TOKEN:
        return False

    try:
        file_info = github_api("GET", f"contents/{FEEDBACK_FILE}")
        current_content = base64.b64decode(file_info["content"]).decode("utf-8")
        sha = file_info["sha"]
    except (urllib.error.HTTPError, RuntimeError):
        current_content = ""
        sha = None

    new_line = json.dumps(feedback, ensure_ascii=False)
    updated_content = current_content + new_line + "\n"

    commit_data = {
        "message": f"feedback: {feedback.get('action', 'unknown')}",
        "content": base64.b64encode(updated_content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        commit_data["sha"] = sha

    github_api("PUT", f"contents/{FEEDBACK_FILE}", commit_data)
    return True


def _send_json(handler, status, data):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _send_json(self, 200, {"ok": True})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            feedback = json.loads(body)
            feedback["server_time"] = datetime.utcnow().isoformat() + "Z"

            saved = False
            error = None
            if GITHUB_TOKEN:
                try:
                    saved = append_feedback(feedback)
                except Exception as e:
                    error = str(e)[:200]

            resp = {"ok": True, "saved_to_github": saved, "timestamp": feedback["server_time"]}
            if error:
                resp["github_error"] = error
            _send_json(self, 200, resp)

        except json.JSONDecodeError:
            _send_json(self, 400, {"ok": False, "error": "Invalid JSON"})
        except Exception as e:
            _send_json(self, 500, {"ok": False, "error": str(e)[:200]})

    def do_GET(self):
        _send_json(self, 200, {"ok": True, "service": "Daily Digest Feedback API"})
