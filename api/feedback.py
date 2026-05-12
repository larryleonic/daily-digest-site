"""
Vercel Serverless Function: POST /api/feedback
接收用户反馈，通过 GitHub API 追加到仓库的 data/feedback.jsonl
"""

import json
import os
import base64
from http.server import BaseHTTPRequestHandler
from datetime import datetime

# 从 Vercel 环境变量读取
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "larryleonic/daily-digest-site")
FEEDBACK_FILE = "data/feedback.jsonl"


def github_api(method: str, endpoint: str, data: dict = None) -> dict:
    """调用 GitHub API"""
    import urllib.request
    import urllib.error

    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "DailyDigest/1.0",
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"GitHub API {e.code}: {error_body[:300]}")


def append_feedback(feedback: dict) -> bool:
    """追加一条反馈到 GitHub 仓库的 feedback.jsonl"""
    if not GITHUB_TOKEN:
        return False

    # 获取当前文件内容和 SHA
    try:
        file_info = github_api("GET", f"contents/{FEEDBACK_FILE}")
        current_content = base64.b64decode(file_info["content"]).decode("utf-8")
        sha = file_info["sha"]
    except RuntimeError:
        # 文件不存在，创建新文件
        current_content = ""
        sha = None

    # 追加新行
    new_line = json.dumps(feedback, ensure_ascii=False)
    updated_content = current_content + new_line + "\n"

    # 提交更新
    commit_data = {
        "message": f"feedback: {feedback.get('action', 'unknown')} @ {feedback.get('timestamp', '')}",
        "content": base64.b64encode(updated_content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        commit_data["sha"] = sha

    github_api("PUT", f"contents/{FEEDBACK_FILE}", commit_data)
    return True


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            feedback = json.loads(body)

            # 添加服务端时间戳
            feedback["server_time"] = datetime.utcnow().isoformat() + "Z"

            # 尝试写入 GitHub
            saved_to_github = False
            if GITHUB_TOKEN:
                try:
                    saved_to_github = append_feedback(feedback)
                except Exception as e:
                    print(f"GitHub API error: {e}")

            response = {
                "ok": True,
                "saved_to_github": saved_to_github,
                "timestamp": feedback["server_time"],
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Invalid JSON"}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)[:200]}).encode())
