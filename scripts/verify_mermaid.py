# -*- coding: utf-8 -*-
"""用 Mermaid 11.13.0 真实解析文档中的 erDiagram，验证语法（playwright + jsDelivr CDN）。"""
import json
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

md_path = Path(r"C:\Users\liuqu\Desktop\Projects\DemandHub\DemandHub_科技需求收集智能体_概念模型与数据库设计_v1.0.md")
md = md_path.read_text(encoding="utf-8")
m = re.search(r"```mermaid\n(.*?)\n```", md, re.S)
if not m:
    print("未找到 mermaid 块"); sys.exit(1)
code = m.group(1)
code_json = json.dumps(code, ensure_ascii=False)

html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.13.0/dist/mermaid.min.js"></script></head>
<body><div id="g"></div>
<script>
const code = {code_json};
mermaid.initialize({{startOnLoad:false}});
(async () => {{
  try {{
    await mermaid.parse(code);
    document.title = "PARSE_OK";
  }} catch(e) {{
    document.title = "PARSE_FAIL: " + (e && e.message ? e.message : String(e));
  }}
}})();
</script></body></html>"""
tmp = Path(__file__).with_name("_mermaid_tmp.html")
tmp.write_text(html, encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(tmp.as_uri())
    page.wait_for_timeout(4000)
    title = page.title()
    browser.close()
tmp.unlink(missing_ok=True)
print(title[:1200])
sys.exit(0 if title.startswith("PARSE_OK") else 1)
