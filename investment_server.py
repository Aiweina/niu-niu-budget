import json
import os
import threading
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8091
ROOT = os.path.dirname(os.path.abspath(__file__))


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
        if self.path.split("?", 1)[0] == "/api/quotes":
            return self.send_quotes()
        return super().do_GET()

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
    url = Path(os.path.join(ROOT, "index.html")).as_uri()
    print("小金庫行情服務已啟動：http://127.0.0.1:8091/api/quotes")
    print("請保留這個視窗；關閉視窗後，行情更新服務也會停止。")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
