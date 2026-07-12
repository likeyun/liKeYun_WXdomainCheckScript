import os
import json
import time
import pyautogui
import pyperclip
import uiautomation as auto
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# 搜索入口图片
SEARCH_BUTTON = "./sousuo.png"
# 地址栏图片
SEARCH_INPUT = "./searchicon.png"
# 检测缓存
CHECK_LOG = "./checklog.json"

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


def load_check_log():
    if not os.path.exists(CHECK_LOG):
        return {}
    try:
        with open(CHECK_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_check_log(data):
    try:
        with open(CHECK_LOG, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存失败:", e)


def get_cache(url):
    """5分钟缓存"""
    logs = load_check_log()
    item = logs.get(url)
    if not item:
        return None
    if time.time() - item["time"] < 300:
        print("读取缓存:", url)
        return item["result"]
    return None


def get_browser():
    desktop = auto.GetRootControl()
    return [c for c in desktop.GetChildren() if c.ClassName == "Chrome_WidgetWin_0"]

def click_image(path, confidence=0.75):
    if not os.path.exists(path):
        raise Exception("图片不存在:" + path)
    pos = pyautogui.locateCenterOnScreen(path, confidence=confidence)
    if not pos:
        raise Exception("没有找到:" + path)
    print("点击:", path, pos)
    pyautogui.moveTo(pos.x, pos.y, duration=0.2)
    pyautogui.click()
    time.sleep(1)


def open_browser():
    controls = get_browser()
    if controls:
        return controls
    print("没有浏览器，点击搜索")
    click_image(SEARCH_BUTTON)
    for i in range(15):
        time.sleep(1)
        controls = get_browser()
        if controls:
            return controls
    return []


def input_url(url):
    click_image(SEARCH_INPUT)
    time.sleep(0.5)
    pyperclip.copy(url)
    pyautogui.hotkey("ctrl", "v")
    pyautogui.press("enter")


def check_page(ctrl):
    time.sleep(3)
    controls = find_all_controls(ctrl)
    texts = []
    for c in controls:
        try:
            if c.Name:
                text = c.Name.strip()
                if text:
                    texts.append(text)
        except:
            pass

    block_keywords = ["如需浏览，请长按网址", "已停止访问该网页", "将要访问", "存在风险", "违规"]
    matched = []
    has_weixin110 = False

    for text in texts:
        if "weixin110.qq.com" in text:
            has_weixin110 = True
        for keyword in block_keywords:
            if keyword in text:
                if text not in matched:
                    matched.append(text)

    if has_weixin110 and matched:
        return {"code": -1, "msg": "拦截", "ret": {"desc": matched}}
    return {"code": 0, "msg": "正常"}


def automate_url(url):

    os.startfile(
        "weixin://"
    )

    time.sleep(1)

    try:
        cache = get_cache(url)
        if cache:
            return cache

        browsers = open_browser()

        if not browsers:
            result = {
                "code": -2,
                "msg": "没有检测窗口",
                "url": url
            }

        else:
            browser = browsers[0]
            input_url(url)
            result = check_page(browser)
            result["url"] = url


        logs = load_check_log()

        logs[url] = {
            "time": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "result": result,
        }

        save_check_log(logs)

        return result

    except Exception as e:

        return {
            "code": -2,
            "msg": str(e),
            "url": url,
            "ret": {}
        }

    finally:
        # 所有流程结束后关闭微信当前页面
        time.sleep(1)
        pyautogui.hotkey(
            "ctrl",
            "shift",
            "w"
        )
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path)
        params = parse_qs(path.query)
        url = params.get("url", [""])[0]

        if not url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json;charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"code": -3, "msg": "缺少url"}, ensure_ascii=False).encode(
                    "utf-8"
                )
            )
            return

        result = automate_url(url)
        self.send_response(200)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    print("启动:", f"http://{host}:{port}")
    server = HTTPServer((host, port), Handler)
    server.serve_forever()