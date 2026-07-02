import uiautomation as auto
import pyautogui
import time
import json
import threading
import queue
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import pyperclip

# ========================
# 任务队列
# ========================
task_queue = queue.Queue()
result_map = {}
lock = threading.Lock()

# ========================
# 控件递归
# ========================
def find_all_controls(control, results=None):
    if results is None:
        results = []

    try:
        if control.Exists(0.1):
            results.append(control)
            try:
                children = control.GetChildren()
            except:
                children = []
            for child in children:
                find_all_controls(child, results)
    except:
        pass

    return results

# ========================
# 单URL执行
# ========================
def automate_url(url):
    class_name_to_search = "Chrome_WidgetWin_0"
    desktop = auto.GetRootControl()
    controls = [c for c in desktop.GetChildren() if c.ClassName == class_name_to_search]

    for ctrl in controls:
        try:
            rect = ctrl.BoundingRectangle
            x = rect.left + 275
            y = rect.top + 15

            pyautogui.moveTo(x, y, duration=0.3)
            pyautogui.click()

            pyperclip.copy(url)
            pyautogui.hotkey("ctrl", "v")
            pyautogui.press("enter")

            time.sleep(2)

            all_controls = find_all_controls(ctrl)
            text_controls = [
                c.Name for c in all_controls
                if c.ControlTypeName == "TextControl" and c.Name
            ]

            title_text = text_controls[0] if text_controls else ""
            desc_text = "，".join(text_controls[1:]) if len(text_controls) > 1 else ""

            blocked_phrases = [
                "如需浏览，请长按网址复制后使用浏览器访问",
                "已停止访问该网页",
                "将要访问"
            ]

            if any(p in title_text for p in blocked_phrases):
                return {"code": -1, "msg": "拦截", "url": url,
                        "ret": {"title": title_text, "desc": desc_text}}

            return {"code": 0, "msg": "正常", "url": url,
                    "ret": {"title": title_text, "desc": desc_text}}

        except Exception as e:
            return {"code": -2, "msg": f"操作失败: {e}", "url": url,
                    "ret": {"title": "", "desc": ""}}

    return {"code": -4, "msg": "未找到控件", "url": url, "ret": {}}

# ========================
# worker（顺序执行）
# ========================
def worker():
    import pythoncom
    pythoncom.CoInitialize()  # 🔥 关键修复

    while True:
        task_id, url = task_queue.get()

        try:
            result = automate_url(url)
            with lock:
                result_map[task_id] = result
        except Exception as e:
            with lock:
                result_map[task_id] = {
                    "code": -500,
                    "msg": str(e),
                    "url": url
                }

        task_queue.task_done()

# ========================
# HTTP Handler（支持批量）
# ========================
class MyHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        url_param = query.get("url", [""])[0]

        if not url_param:
            self.send_response(400)
            self.end_headers()
            return

        url_list = [u.strip() for u in url_param.split(",") if u.strip()]

        # ========================
        # 🔥 SSE 必须头
        # ========================
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # ========================
        # 🔥 逐条执行 + 推送
        # ========================
        for url in url_list:
            task_id = str(time.time_ns())
            task_queue.put((task_id, url))

            # 等待当前任务完成
            while True:
                with lock:
                    if task_id in result_map:
                        result = result_map.pop(task_id)
                        break
                time.sleep(0.05)

            # 🔥 SSE 格式输出
            msg = f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()

        # 结束标记
        self.wfile.write(b"data: {\"msg\":\"done\"}\n\n")
        self.wfile.flush()

# ========================
# 启动 worker
# ========================
if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()

    host = "127.0.0.1"
    port = 8000

    print(f"服务器启动: http://{host}:{port}")
    HTTPServer((host, port), MyHandler).serve_forever()