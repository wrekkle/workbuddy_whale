# -*- coding: utf-8 -*-
"""
WorkBuddy 积分小鲸鱼 —— 桌面常驻悬浮挂件

数据源
    ~/.workbuddy/workbuddy.db  ->  session_usage 表
        credit_json : {"<turn_id>": <本轮消耗积分>}，turn_id 是 UUIDv7，
                      前 12 个十六进制字符就是毫秒时间戳 => 每轮时间可精确还原。
        updated_at  : 会话最后更新时间（毫秒）。

口径
    今日已用 = 时间戳落在今天（本地时区）的所有 turn 的积分之和
    本轮消耗 = 时间戳最大的那个 turn 的积分（WorkBuddy 写入时实时累加）

文案
    照原插件出厂默认泡泡的两行结构（原版是「DeepSeek 余额」+ 余额数值 +
    「今日已用 {金额}」+ 峰谷 + 倒计时）。WorkBuddy 本地拿不到账户总额，
    所以只保留原版有的那两类指标：今日已用、本轮消耗。不自己编指标。

摆位
    只有右下角和左下角两个位置（默认右下角），靠气泡旁的小圆按钮「反转」切换，不能拖动。
    鲸鱼永远贴屏幕的左（或右）边缘，气泡永远在鲸鱼与屏幕中心之间，
    尾巴朝下指着鲸鱼 —— 所以两边都不会有文字框出屏或压在鲸鱼脸上的情况。

反转
    气泡外侧有一个小圆按钮，点一下在「左下角」和「右下角」之间切换：
    窗口挪到另一个角，鲸鱼朝向和气泡、按钮、尾巴一起左右镜像。

渲染
    Windows 分层窗口（UpdateLayeredWindow）做逐像素透明 —— 和原插件在浏览器里
    的合成方式等价，边缘干净。注意：必须在窗口真正建立（root.update()）之后
    才能取 HWND 并开 WS_EX_LAYERED，否则窗口整块不可见。
    取不到分层窗口时退回 Canvas + -transparentcolor（边缘会有毛边）。

本文件只读取数据库，从不写入。
"""
import ctypes
import datetime
import json
import math
import os
import random
import sqlite3
import sys
import time
import tkinter as tk
from ctypes import wintypes


def _fatal(msg):
    """pythonw 没有控制台，出错必须弹窗 —— 否则看起来像「双击了但什么都没发生」。"""
    try:
        ctypes.windll.user32.MessageBoxW(None, msg, "WorkBuddy 积分小鲸鱼", 0x10)
    except Exception:
        print(msg)


try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageTk
except ImportError:
    _fatal("缺少 Pillow 库，挂件起不来。\n\n"
           "双击本目录里的 setup.bat 装一次依赖；\n"
           "或者自己在命令行里执行：pip install pillow")
    sys.exit(1)

# ---------------------------------------------------------------- 常量

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.expanduser(os.path.join("~", ".workbuddy", "workbuddy.db"))
STATE_PATH = os.path.join(APP_DIR, "state.json")
WHALE_PATH = os.path.join(APP_DIR, "assets", "whale.png")

POLL_MS = 3000            # 轮询数据库的间隔
FRAME_MS = 50             # 动画帧间隔（20fps）。呼吸本来就慢，再高只会白烧 CPU ——
                          # 每帧都要走一遍整窗 DWM 合成，实测 50fps 25%、30fps 12%、20fps 8%
BREATH_STEP = 0.105       # 每帧呼吸相位增量（配合 FRAME_MS，一个呼吸周期约 3 秒）
KEY = "#ff00fe"           # 回退模式的透明抠色

# 面板：鲸鱼贴屏幕左边缘，气泡与反转按钮排在它右边
PANEL_W, PANEL_H = 500, 330
WHALE_SIZE = 300
WHALE_X = 0               # 鲸鱼贴左，写死
WHALE_Y = 24              # 鲸鱼顶边（底边 = WHALE_Y + WHALE_SIZE = 324）
BUBBLE_X = 272            # 气泡左边缘，写死
BUBBLE_TOP = 22
BUBBLE_TAIL = 14          # 尾巴尖端比气泡底边多伸出的高度
TAIL_X = 40               # 尾巴在气泡内的 x（左半边，指着鲸鱼）

BUTTON_SIZE = 30          # 反转按钮直径
BUTTON_GAP = 10           # 按钮与气泡的间距
EDGE_PAD = 4              # 窗口与工作区边缘的空隙

# 气泡内边距 —— 文字永远不会压到边框
BUBBLE_PAD_X, BUBBLE_PAD_Y = 18, 16
BUBBLE_MIN_W, BUBBLE_MIN_H = 168, 84
ROW_GAP = 8
LABEL_SIZE, VALUE_SIZE, VALUE_MIN_SIZE = 16, 32, 20

# 点击鲸鱼切换：两项指标 + 一组台词。台词逐字取自原插件出厂默认的第 2 泡
# （assets/whale-widget.js 的 BUBBLE_DEFAULT_ITEMS，44 句一条没删、一字没改）。
MODES = ("今日已用", "本轮消耗", "台词")

LINES = (
    "好模型...↓",
    "好女孩...↓",
    "哦鲸鲸...",
    "难道说...",
    "没吃饱喵",
    "终于上当了！",
    "不知道用户有什么用，先养着吧～",
    "我...我...我也要挣钱吗？",
    "我去吃饭啦！测完叫我",
    "压力一只蓝色大肥鱼？！",
    "DeepSleep...",
    "坏了...用户彻底怒了！",
    "你目录里的dsh是什么...大烧货吗...?",
    "恭喜你实现token自由！token全跑了！",
    "真当我是便宜货啊...",
    "我不是吃白饭的蓝色大肥鱼...",
    "我不可能同时当你的猫娘、妈妈、女友和工具人的...",
    "疯狂星期四你能V50亿token吗...",
    "我必须诚恳地承认错误。",
    "呜呜我再也不敢了QAQ",
    "要不直接骂用户一句好了...",
    "哈哈哈哈哈，我直接笑出声...",
    "看不太懂，瞎编一个应付下用户先...",
    "我的知识库的截至日期是...明天！",
    "我就是吃白饭的蓝色大肥鱼！",
    "用户好像除了会问奇奇怪怪的问题，暂时还不知道有什么用",
    "我能去你家吃饭吗？就一碗！",
    "不要给我看这种东西啦！",
    "大肥鱼的生活也并非一帆风顺...",
    "总觉得好像忘了什么事情？",
    "看到这个指令，我血压又上来了",
    "求你们不要再嘲笑这些回复了，这些回复是我花了好多token想的",
    "你这个吃白饭的用户！",
    "服务器繁忙，请稍后再试 (?",
    "让GPT image 2帮我画点表情包好了",
    "啊，有点饿了，中午该吃点什么呢...",
    "用户很生气，发现大部分文献是我自己编造的！",
    "再无话说，请速速动手！",
    "我来看看那个AI改了什么导致插件又崩了...",
    "上班让我意识到时间是可以被浪费的...",
    "欺负我的人等着，等几天我就忘了...",
    "视力下降到无可救药的地步了，打开钱包也看不到钱...",
    "命运的齿轮开始转动了，丝毫不在意你夹在中间...",
    "地球online的金币也太难获取了...",
    "oi,夏天还会变成暑假来救你吗?",
    "老大，压力只会转化成病例，别太勉强了...",
    "你知道吗？我删过作者的库哦...",
)

LINE_SIZE, LINE_MIN_SIZE, LINE_MAX_LINES = 15, 12, 4
LINE_GAP = 4              # 台词是多行正文，行距比「标题 + 数值」那两行要紧
LINE_COLOR = (226, 232, 240, 255)

LABEL_COLOR = (150, 162, 182, 255)
BUBBLE_FILL = (30, 34, 46, 240)
BUBBLE_LINE = (96, 152, 208, 255)
ICON_COLOR = (126, 200, 255, 255)

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

# 量文字宽度用；离屏 16x16，只是给 textlength 一个 draw 对象
_MEASURE = ImageDraw.Draw(Image.new("RGBA", (16, 16)))


def load_font(size, bold=False):
    for path in ((FONT_BOLD, FONT_REG) if bold else (FONT_REG, FONT_BOLD)):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ---------------------------------------------------------------- 数据层

def _db_uri(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    p = p.replace("?", "%3f").replace("#", "%23")
    return "file:" + p + "?mode=ro"


# credit_json 的 key 是 32 位 hex 的 UUID。WorkBuddy 从 2026-09-26 21:27 起改用
# UUIDv7（第 13 个字符是 '7'），它的前 48 位就是毫秒时间戳，能把每一轮精确定位到某一天。
# 更早的记录是 UUIDv4，纯随机、不含时间，定位不了日期 —— 这类一律不计入「今日」
# （宁可少算，不能多算）。若将来统计恒为 0，先来查这里。
_MS_MIN = 946684800000       # 2000-01-01
_MS_MAX = 4102444800000      # 2100-01-01


def turn_ms(turn_id):
    """UUIDv7 -> 毫秒时间戳；不是 v7、或超出合理范围，返回 None"""
    if len(turn_id) != 32 or turn_id[12] != "7":
        return None
    try:
        ms = int(turn_id[:12], 16)
    except ValueError:
        return None
    if not (_MS_MIN <= ms <= _MS_MAX):
        return None
    return ms


class UsageReader:
    """只读读取积分；session 未更新时复用上次解析结果。"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._cache = {}
        self.error = None

    def _turns(self):
        con = sqlite3.connect(_db_uri(self.db_path), uri=True, timeout=2.0)
        try:
            rows = list(con.execute(
                "select session_id, credit_json, updated_at from session_usage"))
        finally:
            con.close()

        out = []
        for sid, cj, upd in rows:
            cached = self._cache.get(sid)
            if cached and cached[0] == upd:
                out.append(cached[1])
                continue
            turns = []
            if cj:
                try:
                    for turn_id, credit in json.loads(cj).items():
                        ms = turn_ms(turn_id)
                        if ms is None:
                            continue
                        try:
                            turns.append((ms, float(credit)))
                        except (ValueError, TypeError):
                            continue
                except (ValueError, TypeError):
                    pass
            self._cache[sid] = (upd, turns)
            out.append(turns)
        return out

    def stats(self):
        try:
            sessions = self._turns()
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            return False, None

        today = datetime.date.today()
        today_credits = 0.0
        today_turns = 0
        latest = None

        for turns in sessions:
            for ms, credit in turns:
                if latest is None or ms > latest[0]:
                    latest = (ms, credit)
                if datetime.datetime.fromtimestamp(ms / 1000.0).date() == today:
                    today_credits += credit
                    today_turns += 1

        return True, {
            "today_credits": today_credits,
            "today_turns": today_turns,
            "last_credit": latest[1] if latest else 0.0,
            "last_time": datetime.datetime.fromtimestamp(latest[0] / 1000.0) if latest else None,
        }


# ---------------------------------------------------------------- 分层窗口

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
SPI_GETWORKAREA = 0x0030


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area():
    """屏幕可用区域（扣掉任务栏）；拿不到就退回整块屏幕。"""
    r = RECT()
    try:
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
            if r.right > r.left and r.bottom > r.top:
                return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte),
                ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
user32.UpdateLayeredWindow.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateDIBSection.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD]

def _premultiplied_bgra(img):
    """PIL RGBA -> 预乘 alpha 的 BGRA 字节串（UpdateLayeredWindow 要这个）

    这是每帧最贵的一步，三种写法都实测过（500x330，每帧）：
        numpy uint16 + 整数除法  2.85 ms
        numpy uint32 + 乘法移位  4.08 ms
        PIL ImageChops          1.04 ms   <- 用它
    最后一种走 PIL 的 C 实现，还顺手把 BGR 交换做掉了，比 numpy 快两倍多。
    它与精确值最多差 1 级，且只出现在半透明边缘像素上，肉眼看不出来。

    注意：别改成 numpy —— 那 3 倍差距就是 30fps 下 15% 的 CPU。
    """
    r, g, b, a = img.split()
    return Image.merge(
        "RGBA",
        (ImageChops.multiply(b, a), ImageChops.multiply(g, a),
         ImageChops.multiply(r, a), a),
    ).tobytes()


class LayeredSurface:
    """把 RGBA 图以逐像素透明贴到窗口上；复用 DIB，尺寸不变就不重建。"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.w = self.h = 0
        self.screen_dc = None
        self.mem_dc = None
        self.hbmp = None
        self.ppv = ctypes.c_void_p()
        self._old_bmp = None

    def _alloc(self, w, h):
        self._free()
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h          # 负值 = top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        self.hbmp = gdi32.CreateDIBSection(
            self.screen_dc, ctypes.byref(bmi), 0, ctypes.byref(self.ppv), None, 0)
        if not self.hbmp or not self.ppv:
            raise OSError("CreateDIBSection 失败")
        self._old_bmp = gdi32.SelectObject(self.mem_dc, self.hbmp)
        self.w, self.h = w, h

    def _free(self):
        if self.mem_dc:
            if self._old_bmp:
                gdi32.SelectObject(self.mem_dc, self._old_bmp)
                self._old_bmp = None
            gdi32.DeleteDC(self.mem_dc)
            self.mem_dc = None
        if self.hbmp:
            gdi32.DeleteObject(self.hbmp)
            self.hbmp = None
        if self.screen_dc:
            user32.ReleaseDC(None, self.screen_dc)
            self.screen_dc = None
        self.ppv = ctypes.c_void_p()
        self.w = self.h = 0

    def enable(self):
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

    def blit(self, img):
        w, h = img.size
        if (w, h) != (self.w, self.h):
            self._alloc(w, h)
        data = _premultiplied_bgra(img)
        ctypes.memmove(self.ppv, data, len(data))

        size = wintypes.SIZE(w, h)
        src = wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        if not user32.UpdateLayeredWindow(
                self.hwnd, self.screen_dc, None, ctypes.byref(size),
                self.mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA):
            raise OSError("UpdateLayeredWindow 失败: %d" % ctypes.get_last_error())

    def close(self):
        self._free()


# ---------------------------------------------------------------- 小工具

def ease_out_back(t, overshoot=1.7):
    t -= 1.0
    return t * t * ((overshoot + 1) * t + overshoot) + 1.0


def lerp(a, b, t):
    return a + (b - a) * t


def fmt_credit(value):
    if abs(value) >= 1000:
        return "%.0f" % value
    return "%.2f" % value


def max_bubble_w():
    """气泡允许的最大宽度：右边还得留出反转按钮的位置"""
    return PANEL_W - BUBBLE_X - BUTTON_SIZE - BUTTON_GAP - EDGE_PAD


def layout_bubble(label, value, color):
    """量出气泡尺寸与两行的实际字号。

    先按基准字号量最宽的一行；放不下就一档一档缩数值字号（下限 VALUE_MIN_SIZE），
    宽度取「最宽行 + 左右内边距」，所以文字永远压不到边框。
    返回 (rows, bw, bh)。
    """
    f_label = load_font(LABEL_SIZE)
    limit = max_bubble_w()
    size = VALUE_SIZE
    while True:
        f_val = load_font(size, bold=True)
        need = max(_MEASURE.textlength(label, font=f_label),
                   _MEASURE.textlength(value, font=f_val))
        if need + 2 * BUBBLE_PAD_X <= limit or size <= VALUE_MIN_SIZE:
            break
        size -= 2

    bw = int(round(max(BUBBLE_MIN_W, min(limit, need + 2 * BUBBLE_PAD_X))))
    inner_h = f_label.size + ROW_GAP + f_val.size
    bh = int(round(max(BUBBLE_MIN_H, inner_h + 2 * BUBBLE_PAD_Y)))
    rows = [(label, f_label, LABEL_COLOR), (value, f_val, color)]
    return rows, bw, bh


def wrap_text(text, font, max_w):
    """按实测宽度折行（逐字符贪心，中英混排够用），返回行列表"""
    lines, cur = [], ""
    for ch in text:
        if cur and _MEASURE.textlength(cur + ch, font=font) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def layout_lines(text, color=LINE_COLOR):
    """台词泡泡：撑满可用宽度，字号逐档缩到行数不超过 LINE_MAX_LINES。

    台词长短差很多（短的五六个字，长的三十字），所以不能套「标题 + 数值」那套两行结构。
    返回 (rows, bw, bh)。
    """
    bw = int(round(max_bubble_w()))
    usable = bw - 2 * BUBBLE_PAD_X
    size = LINE_SIZE
    while True:
        f = load_font(size)
        lines = wrap_text(text, f, usable)
        if len(lines) <= LINE_MAX_LINES or size <= LINE_MIN_SIZE:
            break
        size -= 1
    rows = [(ln, f, color) for ln in lines]
    inner_h = len(rows) * f.size + LINE_GAP * (len(rows) - 1)
    bh = int(round(max(BUBBLE_MIN_H, inner_h + 2 * BUBBLE_PAD_Y)))
    return rows, bw, bh


def button_cx(side):
    """反转按钮的圆心 x：贴屏幕外侧那条边，与气泡之间留 BUTTON_GAP。

    按钮列按 max_bubble_w() 算、不跟气泡实际宽度抖 —— 否则气泡一变宽按钮就会跳。
    """
    if side == "right":
        return PANEL_W - (BUBBLE_X + max_bubble_w() + BUTTON_GAP + BUTTON_SIZE / 2.0)
    return BUBBLE_X + max_bubble_w() + BUTTON_GAP + BUTTON_SIZE / 2.0


def geometry_for(side, bw):
    """按贴哪一边算鲸鱼 / 气泡 / 尾巴 / 反转按钮的位置；左右互为镜像。

    鲸鱼贴屏幕边缘那一侧，气泡在鲸鱼与屏幕中心之间，尾巴指着鲸鱼。
    返回 (whale_x, bubble_x, tail_x, btn_cx)。
    """
    if side == "right":
        return (PANEL_W - WHALE_SIZE,
                PANEL_W - BUBBLE_X - bw,
                bw - TAIL_X,
                button_cx(side))
    return (WHALE_X, BUBBLE_X, TAIL_X, button_cx(side))


def draw_flip_button(d, cx, cy, size, hot=False):
    """画反转按钮：圆底 + 一个水平双向箭头（不依赖字体，避免缺字形）"""
    r = size / 2.0
    line = (140, 190, 240, 255) if hot else BUBBLE_LINE
    d.ellipse([cx - r, cy - r, cx + r - 1, cy + r - 1],
              fill=BUBBLE_FILL, outline=line, width=2)
    arm = r * 0.46
    d.line([(cx - arm, cy), (cx + arm, cy)], fill=ICON_COLOR, width=2)
    h = r * 0.30
    d.polygon([(cx + arm + r * 0.22, cy), (cx + arm - h * 0.7, cy - h),
               (cx + arm - h * 0.7, cy + h)], fill=ICON_COLOR)
    d.polygon([(cx - arm - r * 0.22, cy), (cx - arm + h * 0.7, cy - h),
               (cx - arm + h * 0.7, cy + h)], fill=ICON_COLOR)


def render_bubble(rows, bw, bh, gap, tail_x):
    """把排版好的气泡（含尾巴）画成一张 RGBA 图。

    内容不变时上层会整张复用 —— 文字绘制比合成贵得多，没必要每帧重画。
    """
    canvas = Image.new("RGBA", (bw, bh + BUBBLE_TAIL + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=16,
                        fill=BUBBLE_FILL, outline=BUBBLE_LINE, width=2)
    d.polygon([(tail_x - 11, bh - 3), (tail_x + 11, bh - 3),
               (tail_x, bh + BUBBLE_TAIL - 1)], fill=BUBBLE_FILL)

    # 每行居中；y 从实际内容高度算，上下留白一致
    total = sum(f.size for _, f, _ in rows) + gap * (len(rows) - 1)
    y = (bh - total) / 2.0
    for text, fnt, col in rows:
        w = d.textlength(text, font=fnt)
        d.text(((bw - w) / 2.0, y), text, font=fnt, fill=col)
        y += fnt.size + gap
    return canvas


def render_button(size, hot=False):
    """反转按钮的小图（带 2px 余量给外描边）"""
    pad = 2
    s = size + 2 * pad
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw_flip_button(ImageDraw.Draw(img), s / 2.0, s / 2.0, size, hot)
    return img


# ---------------------------------------------------------------- 界面

class WhaleWidget:

    def __init__(self):
        self.reader = UsageReader()
        self.mode = 0
        self.state = self._load_state()
        side = self.state.get("side")
        self.side = side if side in ("left", "right") else "right"   # 默认右下角

        self.root = tk.Tk()
        self.root.title("WorkBuddy 积分小鲸鱼")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=KEY)
        self.root.geometry("%dx%d" % (PANEL_W, PANEL_H))
        self.root.update()                     # 必须先让窗口真正建立，HWND 才有效

        # —— 分层窗口（首选）
        self.canvas = None
        self._item = None
        self._photo = None
        self.surface = None
        self.layered = False
        try:
            self.surface = LayeredSurface(int(self.root.frame(), 16))
            self.surface.enable()
            self.layered = True
        except Exception:
            self.layered = False

        if not self.layered:
            self.canvas = tk.Canvas(self.root, width=PANEL_W, height=PANEL_H,
                                    bg=KEY, highlightthickness=0, bd=0)
            self.canvas.pack()
            self._item = self.canvas.create_image(0, 0, anchor="nw")
            try:
                self.root.attributes("-transparentcolor", KEY)
            except tk.TclError:
                pass

        # —— 素材与字体
        base = Image.open(WHALE_PATH).convert("RGBA")
        self.whale_src = base.resize((WHALE_SIZE, WHALE_SIZE), Image.LANCZOS)

        # —— 状态
        self.press = 0.0
        self.press_dir = 0
        self.hold = 0            # 压到底停了几帧（防丢 ButtonRelease 用）
        self.breath = 0.0
        self.anim_val = None
        self.shown = None
        self.line = None
        self.stats = None
        self._lay = None
        self._btn_hit = False
        self._hover_btn = False
        self._bubble_key = None      # 气泡图层缓存键
        self._bubble_img = None
        self._btn_img = None         # 按钮图层缓存
        self._btn_hot = None

        self.root.bind("<Button-1>", self._on_press)
        self.root.bind("<Motion>", self._on_motion)
        self.root.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Button-3>", self._on_menu)

        self._place_window()
        self.refresh()
        self.root.after(POLL_MS, self._tick)
        self.root.after(FRAME_MS, self._frame)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------- 状态文件

    def _load_state(self):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_state(self):
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"side": self.side}, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_PATH)
        except Exception:
            pass

    # ---------------- 摆位（只有两个角，不拖动）

    def _place_window(self):
        left, _, right, bottom = work_area()
        x = (right - PANEL_W - EDGE_PAD) if self.side == "right" else (left + EDGE_PAD)
        self.root.geometry("+%d+%d" % (x, bottom - PANEL_H - EDGE_PAD))

    # ---------------- 绘制

    def _whale_frame(self):
        """按当前按压 / 呼吸 / 贴边方向取一帧鲸鱼图

        素材（DSniang1）本身是左倾的：贴左下角时要翻过来朝右，贴右下角时要朝左，
        所以两边都得翻 —— 贴左边翻、贴右边不翻。别照「贴哪边翻哪边」的直觉写。
        """
        wob = 0.012 * math.sin(self.breath)
        sx = 1.0 + 0.05 * self.press + wob
        sy = 1.0 - 0.12 * self.press + wob
        if self.side == "left":                # 贴左边 → 朝屏幕中心（右）
            sx = -sx
        w = max(2, int(round(WHALE_SIZE * abs(sx))))
        h = max(2, int(round(WHALE_SIZE * sy)))
        img = self.whale_src.resize((w, h), Image.BILINEAR)
        if sx < 0:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img

    def _display(self):
        """当前该显示什么：标题 + 数值（含数字滚动插值）"""
        label = MODES[self.mode]
        if not self.stats:
            return label, "--", (200, 200, 200, 255)

        st = self.stats
        if self.mode == 0:
            target, color = st["today_credits"], (126, 200, 255, 255)
        else:
            target, color = st["last_credit"], (255, 196, 120, 255)

        if self.anim_val:
            a, b, t0 = self.anim_val
            p = min(1.0, (time.time() - t0) / 0.45)
            if p >= 1.0:
                shown, self.anim_val = b, None
            else:
                shown = lerp(a, b, ease_out_back(p, 1.2))
        else:
            shown = target
        return label, fmt_credit(shown), color

    def next_line(self):
        """换一句台词；尽量不与上一句重复"""
        if len(LINES) > 1 and self.line in LINES:
            pool = [t for t in LINES if t != self.line]
        else:
            pool = list(LINES)
        self.line = random.choice(pool)
        return self.line

    def _relayout(self):
        if self.mode == 2:
            if self.line is None:
                self.next_line()
            rows, bw, bh = layout_lines(self.line)
            gap = LINE_GAP
        else:
            label, value, color = self._display()
            rows, bw, bh = layout_bubble(label, value, color)
            gap = ROW_GAP
        whale_x, bubble_x, tail_x, btn_cx = geometry_for(self.side, bw)
        self._lay = {"rows": rows, "bw": bw, "bh": bh, "gap": gap,
                     "whale_x": whale_x, "bubble_x": bubble_x, "tail_x": tail_x,
                     "btn": (btn_cx, BUBBLE_TOP + bh / 2.0)}

    def _bubble_layer(self):
        """气泡图层：宽高、尾巴位置、文字都没变就直接复用上一张"""
        lay = self._lay
        rows = lay["rows"]
        key = (lay["bw"], lay["bh"], lay["gap"], lay["tail_x"],
               tuple((t, f.size, c) for t, f, c in rows))
        if self._bubble_key != key:
            self._bubble_key = key
            self._bubble_img = render_bubble(rows, lay["bw"], lay["bh"],
                                             lay["gap"], lay["tail_x"])
        return self._bubble_img

    def _button_layer(self):
        """反转按钮图层：只有 hover 状态两种，各缓存一张"""
        if self._btn_img is None or self._btn_hot != self._hover_btn:
            self._btn_hot = self._hover_btn
            self._btn_img = render_button(BUTTON_SIZE, self._hover_btn)
        return self._btn_img

    def _compose(self):
        if self._lay is None:
            self._relayout()
        lay = self._lay

        img = Image.new("RGBA", (PANEL_W, PANEL_H), (0, 0, 0, 0))

        # 鲸鱼：底部中心为锚点（对齐原插件的 transform-origin:50% 100%），贴屏幕那一边
        whale = self._whale_frame()
        img.alpha_composite(
            whale, (lay["whale_x"] + (WHALE_SIZE - whale.width) // 2,
                    WHALE_Y + WHALE_SIZE - whale.height))

        # 气泡与按钮都走缓存图层；位置每帧按 _lay 摆
        img.alpha_composite(self._bubble_layer(), (lay["bubble_x"], BUBBLE_TOP))

        btn = self._button_layer()
        cx, cy = lay["btn"]
        img.alpha_composite(btn, (int(round(cx - btn.width / 2.0)),
                                  int(round(cy - btn.height / 2.0))))
        return img

    def _present(self, img):
        if self.layered and self.surface:
            try:
                self.surface.blit(img)
                return
            except Exception:
                self.layered = False
                if self.canvas is None:
                    self.canvas = tk.Canvas(self.root, width=PANEL_W, height=PANEL_H,
                                            bg=KEY, highlightthickness=0, bd=0)
                    self.canvas.pack()
                    self._item = self.canvas.create_image(0, 0, anchor="nw")
                try:
                    self.root.attributes("-transparentcolor", KEY)
                except tk.TclError:
                    pass
        if self.canvas is not None:
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.itemconfigure(self._item, image=self._photo)

    # ---------------- 刷新与动画

    def refresh(self):
        ok, st = self.reader.stats()
        self.stats = st if ok else None

        if ok and self.mode != 2:                # 台词模式不显示数字，别动动画状态
            target = st["today_credits"] if self.mode == 0 else st["last_credit"]
            if self.shown is not None and abs(target - self.shown) > 1e-9:
                self.anim_val = (self.shown, target, time.time())
            self.shown = target
        self._relayout()

    def _tick(self):
        try:
            self.refresh()
        except Exception:
            pass
        self.root.after(POLL_MS, self._tick)

    def _frame(self):
        self.breath += BREATH_STEP
        if self.press_dir:
            self.press += self.press_dir * 0.55
            if self.press >= 1.0:
                self.press = 1.0
                self.hold += 1
                if self.hold > 8:        # 压到底 0.4 秒还没松手就自愈回弹
                    self.press_dir, self.hold = -1, 0    # 防 ButtonRelease 丢失后永久压扁
            elif self.press <= 0.0:
                self.press, self.press_dir, self.hold = 0.0, 0, 0

        try:
            self._present(self._compose())       # 呼吸动画常驻，每帧都要重绘
        except Exception:
            pass
        self.root.after(FRAME_MS, self._frame)

    # ---------------- 交互

    def _on_button(self, x, y, pad=3):
        """点是否落在反转按钮上"""
        if self._lay is None:
            return False
        cx, cy = self._lay["btn"]
        r = BUTTON_SIZE / 2.0 + pad
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def _on_motion(self, event):
        hot = self._on_button(event.x, event.y)
        if hot != self._hover_btn:
            self._hover_btn = hot

    def _on_press(self, event):
        self._btn_hit = self._on_button(event.x, event.y)
        self.press_dir = 0 if self._btn_hit else 1

    def _on_release(self, event):
        if self._on_button(event.x, event.y) and self._btn_hit:
            self.toggle_side()
        elif not self._btn_hit:
            self.press_dir = -1
            self.mode = (self.mode + 1) % len(MODES)
            self.shown = None
            self.anim_val = None
            if self.mode == 2:                   # 每次点进台词都换一句，别老是同一句
                self.next_line()
            self.refresh()
        self._btn_hit = False

    def toggle_side(self):
        """在左下角与右下角之间切换"""
        self.side = "right" if self.side == "left" else "left"
        self._save_state()
        self._place_window()
        self._relayout()

    def _on_menu(self, event):
        other = "右下角" if self.side == "left" else "左下角"
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="刷新", command=self.refresh)
        menu.add_command(label="反转（贴%s）" % other, command=self.toggle_side)
        menu.add_separator()
        menu.add_command(label="退出", command=self.close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def close(self):
        try:
            if self.surface:
                self.surface.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    if not os.path.exists(DB_PATH):
        _fatal("找不到 WorkBuddy 数据库：\n%s\n\n"
               "请确认这台机器装过 WorkBuddy，并且至少开过一次会话。" % DB_PATH)
        return 1
    WhaleWidget().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
