# WorkBuddy Credit Whale 🐋

![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6?style=flat-square)
![python](https://img.shields.io/badge/python-3.8%2B-3776AB?style=flat-square)
![deps](https://img.shields.io/badge/deps-Pillow-ffd43b?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![stars](https://img.shields.io/github/stars/wrekkle/workbuddy_whale?style=flat-square)

**Your WorkBuddy credit usage, as a whale that lives in the corner of your screen.**
把 WorkBuddy 的积分消耗做成一只常驻屏幕角落的小鲸鱼 —— 会呼吸、会报数、偶尔说句怪话。

![demo](docs/demo.gif)

本来只是 DeepSeek 那个插件上的鲸鱼。后来想想，积分就躺在本地 sqlite 里，不如让她爬出来，站在桌面上。

## 它干什么

- 贴屏幕角落、常驻最上层，**逐像素透明** —— 没有白底方框，也没有一圈紫毛边。
- 三种显示，点一下鲸鱼循环切换：**今日已用** / **本轮消耗** / **台词**（台词共 47 句，随机不重复）。
- 点气泡旁边的圆按钮：在**左下角 / 右下角**之间整体镜像 —— 鲸鱼朝向、气泡、尾巴、按钮一起翻。
- 右键退出。位置记在 `state.json`，下次开还是上次那个角。
- 开机自启。

数据只从本机的 `%USERPROFILE%\.workbuddy\workbuddy.db` 读，**只读、不写库、不联网、不上传**。

## 跑起来

需要 Windows + Python 3（`tkinter` 是标准库自带的，额外的依赖只有 Pillow）：

    git clone https://github.com/wrekkle/workbuddy_whale.git
    cd workbuddy_whale

    1. 装 Python 3 —— 安装时务必勾上 "Add python.exe to PATH"
    2. 双击 setup.bat        ← 装 Pillow + 在「启动」文件夹建快捷方式
    3. 双击 start-whale.vbs  ← 鲸鱼出现

不想用 `setup.bat` 也可以手动两步：

    pip install pillow
    pythonw whale.py

`pythonw` 没有控制台，所以**出错时会弹窗**告诉你缺什么，不会静悄悄什么都不发生。

## 数字是怎么算的

| 指标 | 口径 |
| --- | --- |
| 今日已用 | 时间戳落在今天（本地时区）的所有对话轮次的积分之和 |
| 本轮消耗 | 时间戳最大的那一轮的积分 |

`session_usage.credit_json` 的 key 是 UUIDv7，**前 12 个十六进制字符就是毫秒时间戳**，所以每一轮都能精确定位到某一天，不用靠 `updated_at` 猜。WorkBuddy 从 2026-09-26 21:27 起才改用 v7，更早的记录是 v4（纯随机、不含时间），那部分一律不计入「今日」—— 宁可少算，不能多算。

## 长什么样

| 右下角 · 显示数字 | 左下角 · 说台词 |
| --- | --- |
| ![right](docs/preview.png) | ![left](docs/preview-left.png) |

## 兼容性与已知边界

- Windows 10 / 11。分层窗口（`UpdateLayeredWindow`）拿不到时自动退回 `-transparentcolor`，那时角色边缘会有毛边。
- 任务栏设成「自动隐藏」时系统工作区不会扣掉它，挂件下半身会被弹出来的任务栏压住（任务栏永远在最上层，改不了）。
- 「今日已用」显示 0 有两种正常情况：今天还没跑过对话，或者本机记录早于 2026-09-26。
- 高 DPI 多屏下程序会在建窗口**之前**调 `SetProcessDpiAwareness(2)`；没生效的话尺寸会整体偏小。

## 出问题先看这里

| 现象 | 怎么办 |
| --- | --- |
| 弹窗「缺少 Pillow 库」 | 双击 `setup.bat`，或手动 `pip install pillow` |
| 弹窗「找不到 WorkBuddy 数据库」 | 这台机器没装 WorkBuddy，或者一次会话都没开过 |
| 弹窗「No pythonw.exe found」 | Python 装的时候没勾 "Add python.exe to PATH"，重装一次并勾上 |
| 「今日已用」一直是 0 | 今天还没跑过对话；或本机记录早于 2026-09-26，见上一节 |
| 鲸鱼位置偏了 / 被任务栏压住 | 任务栏设的是「自动隐藏」，见上一节 |

## 文件

    whale.py           主程序（单体，约 930 行，只读数据库）
    assets/whale.png   角色素材
    assets/whale.ico   图标（16→256 七档，给快捷方式用）
    start-whale.vbs    双击启动，自己找 pythonw.exe
    setup.bat          一次性安装：Pillow + 开机自启
    docs/              README 用的截图与动图

## 实现上值得一提的两点

- **逐像素透明**：走 Win32 分层窗口 `UpdateLayeredWindow` + 预乘 BGRA，而不是 `-transparentcolor` 抠色。抠色会在抗锯齿边缘留下一圈底色（紫边），分层窗口不会。
- **预乘用 PIL 而不是 numpy**：`ImageChops.multiply` 在 500×330 的图上单帧 1.04 ms，比 numpy 快一倍多，还少一个依赖。配合 20fps 的帧率，本人机器上 CPU 占用约 6%、内存 42 MB。

## Credits

- 角色形象与气泡台词取自 **DeepSeek 的 `dsh-whale-widget`**（DSH bundle 插件），原样复用，版权归原作者。
- 本仓库的代码（`whale.py`、`setup.bat`、`start-whale.vbs` 等）以 MIT 发布。

## License

MIT
