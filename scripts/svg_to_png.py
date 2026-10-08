# -*- coding: utf-8 -*-
"""将 SVG 渲染为 PNG（playwright 无头浏览器截图，尺寸自动取自 SVG）。
用法：python svg_to_png.py [svg_path] [png_path]（默认 E-R 图）。"""
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(r"C:\Users\liuqu\Desktop\Projects\DemandHub")
svg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "DemandHub_科技需求收集智能体_ER图.svg"
png_path = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "DemandHub_科技需求收集智能体_ER图.png"

svg_text = svg_path.read_text(encoding="utf-8")
m = re.search(r'<svg[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', svg_text)
if not m:
    raise SystemExit("无法从 SVG 解析尺寸")
W, H = int(m.group(1)), int(m.group(2))

html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#ffffff;">
<img src="{svg_path.as_uri()}" width="{W}" height="{H}">
</body></html>"""
tmp = Path(__file__).with_name("_er_png_tmp.html")
tmp.write_text(html, encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": W, "height": H})
    page.goto(tmp.as_uri())
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(png_path), full_page=False)
    browser.close()

tmp.unlink(missing_ok=True)
print("PNG 生成:", png_path, "字节数:", png_path.stat().st_size)
