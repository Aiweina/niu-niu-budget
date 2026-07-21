import json
import os
import threading
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


HOST = "127.0.0.1"
PORT = 8091
ROOT = os.path.dirname(os.path.abspath(__file__))
NOTION_VERSION = "2026-03-11"
CONFIG_PATH = os.path.join(ROOT, "notion_config.local.json")


def load_notion_config():
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file:
                config = json.load(file)
        except (OSError, json.JSONDecodeError):
            config = {}
    return {
        "token": os.environ.get("NOTION_API_TOKEN") or config.get("token", ""),
        "parent_page_id": os.environ.get("NOTION_PARENT_PAGE_ID")
        or config.get("parent_page_id", ""),
    }


def notion_request(method, path, payload=None):
    config = load_notion_config()
    if not config["token"] or not config["parent_page_id"]:
        raise RuntimeError("Notion 尚未設定，請先完成 notion_config.local.json")
    body = None
    headers = {
        "Authorization": f"Bearer {config['token']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "LittleVault/1.0",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.notion.com/v1{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error)
            message = detail.get("message") or str(error)
        except (ValueError, json.JSONDecodeError):
            message = str(error)
        raise RuntimeError(f"Notion API：{message}") from error


def notion_code_blocks(text):
    # Notion rich_text 每段最多 2,000 字元，保留餘裕切成 1,800 字元。
    chunks = [text[index : index + 1800] for index in range(0, len(text), 1800)]
    return [
        {
            "object": "block",
            "type": "code",
            "code": {
                "language": "json",
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
            },
        }
        for chunk in chunks
    ]


def append_notion_blocks(block_id, blocks):
    for index in range(0, len(blocks), 100):
        notion_request(
            "PATCH",
            f"/blocks/{block_id}/children",
            {"children": blocks[index : index + 100]},
        )


def list_block_children(block_id):
    results = []
    cursor = None
    while True:
        suffix = f"?page_size=100&start_cursor={cursor}" if cursor else "?page_size=100"
        response = notion_request("GET", f"/blocks/{block_id}/children{suffix}")
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            return results
        cursor = response.get("next_cursor")


def latest_backup_page():
    parent_id = load_notion_config()["parent_page_id"]
    pages = [
        block
        for block in list_block_children(parent_id)
        if block.get("type") == "child_page"
        and block.get("child_page", {}).get("title", "").startswith("牛牛預算備份｜")
    ]
    if not pages:
        raise RuntimeError("Notion 中尚未找到牛牛預算備份")
    return max(pages, key=lambda page: page.get("child_page", {}).get("title", ""))


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "LittleVault/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def number(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def display_date(value):
    text = str(value or "").strip()
    if len(text) == 7 and text.isdigit():
        return f"{int(text[:3]) + 1911}-{text[3:5]}-{text[5:7]}"
    return text


class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/quotes":
            return self.send_quotes()
        if path == "/api/notion/status":
            config = load_notion_config()
            return self.send_json(
                200,
                {
                    "configured": bool(config["token"] and config["parent_page_id"]),
                    "storage": "Notion",
                },
            )
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/notion/backup":
            return self.backup_to_notion()
        if path == "/api/notion/restore":
            return self.restore_from_notion()
        return self.send_json(404, {"error": "找不到 API"})

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 2_000_000:
            raise ValueError("備份資料大小不正確或超過 2 MB")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def backup_to_notion(self):
        try:
            payload = self.read_json_body()
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("備份內容格式不正確")
            timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H-%M-%S")
            envelope = json.dumps(
                {"version": 1, "saved_at": datetime.now(timezone.utc).isoformat(), "data": data},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            config = load_notion_config()
            page = notion_request(
                "POST",
                "/pages",
                {
                    "parent": {"type": "page_id", "page_id": config["parent_page_id"]},
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [
                                {
                                    "type": "text",
                                    "text": {"content": f"牛牛預算備份｜{timestamp}"},
                                }
                            ],
                        }
                    },
                },
            )
            append_notion_blocks(page["id"], notion_code_blocks(envelope))
            self.send_json(200, {"ok": True, "saved_at": timestamp, "page_id": page["id"]})
        except (ValueError, RuntimeError, urllib.error.URLError) as error:
            self.send_json(502, {"error": str(error)})

    def restore_from_notion(self):
        try:
            page = latest_backup_page()
            chunks = []
            for block in list_block_children(page["id"]):
                if block.get("type") != "code":
                    continue
                chunks.extend(
                    item.get("plain_text", "")
                    for item in block.get("code", {}).get("rich_text", [])
                )
            envelope = json.loads("".join(chunks))
            if not isinstance(envelope.get("data"), dict):
                raise ValueError("Notion 備份內容不完整")
            self.send_json(
                200,
                {
                    "ok": True,
                    "saved_at": envelope.get("saved_at", ""),
                    "data": envelope["data"],
                },
            )
        except (ValueError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as error:
            self.send_json(502, {"error": str(error)})

    def send_quotes(self):
        try:
            twse = fetch_json(
                "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            )
            tpex = fetch_json(
                "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
            )
            quotes = {}
            dates = []
            for row in twse:
                code = str(row.get("Code", "")).strip().upper()
                price = number(row.get("ClosingPrice"))
                if code and price > 0:
                    quotes[code] = {
                        "price": price,
                        "name": row.get("Name", ""),
                        "market": "上市",
                    }
                if row.get("Date"):
                    dates.append(str(row["Date"]))
            for row in tpex:
                code = str(row.get("SecuritiesCompanyCode", "")).strip().upper()
                price = number(row.get("Close"))
                if code and price > 0:
                    quotes[code] = {
                        "price": price,
                        "name": row.get("CompanyName", ""),
                        "market": "上櫃",
                    }
                if row.get("Date"):
                    dates.append(str(row["Date"]))
            body = json.dumps(
                {"quotes": quotes, "date": display_date(max(dates)) if dates else ""},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as error:
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        if self.path.startswith("/api/"):
            super().log_message(format, *args)


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    url = f"http://{HOST}:{PORT}/"
    print("小金庫行情服務已啟動：http://127.0.0.1:8091/api/quotes")
    print("Notion 雲端備份服務：http://127.0.0.1:8091/api/notion/status")
    print("請保留這個視窗；關閉視窗後，行情更新服務也會停止。")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
