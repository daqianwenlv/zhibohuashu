# 这是什么：直播话术「景区资料」上传解析——把上传的文件（Word、PDF、Excel、PPT、文本、图片）或链接（飞书文档、飞书表格、知识库、普通网页）解析成文字，追加进项目的景区资料
# 谁用：/opt/ai-office/auth_server.py 的 /api/zhubo/material-file、/api/zhubo/material-link；原件存 /opt/ai-office/zhubo/uploads/<项目>/，来源清单 /opt/ai-office/zhubo/data/<项目>_sources.json
# 什么时候改：要支持新的文件或链接类型；飞书走 y1y1 本机 lark-cli（用户本人授权）
import base64, csv, html, io, json, os, re, subprocess, tempfile, time, urllib.request, zipfile

WORK = "/opt/ai-office/zhubo/data"
UP = "/opt/ai-office/zhubo/uploads"
MAX = 60000


def _xml_text(x):
    x = re.sub(r"</w:p>|</a:p>|<w:br/>|<w:tab/>", "\n", x)
    return html.unescape(re.sub(r"<[^>]+>", "", x))


def parse_file(name, data):
    ext = os.path.splitext(name.lower())[1]
    if ext in (".txt", ".md", ".csv", ".json"):
        for enc in ("utf-8", "gb18030"):
            try: return data.decode(enc)
            except Exception: pass
    if ext == ".docx":
        return _xml_text(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8"))
    if ext == ".pptx":
        z = zipfile.ZipFile(io.BytesIO(data))
        slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
        return "\n\n".join("【第%d页】\n%s" % (i + 1, _xml_text(z.read(n).decode("utf-8")).strip()) for i, n in enumerate(slides))
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            rows = ["\t".join("" if v is None else str(v) for v in r) for r in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if r.strip()]
            if rows: out.append("【表：%s】\n%s" % (ws.title, "\n".join(rows[:2000])))
        return "\n\n".join(out)
    if ext == ".pdf":
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.pdf"); open(src, "wb").write(data)
            r = subprocess.run(["/root/bin/pdf2md", src, "-"], capture_output=True, text=True, timeout=900)
            if r.returncode != 0 or not r.stdout.strip(): raise ValueError("PDF 没读出文字")
            return r.stdout
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return ocr_image(data, ext)
    raise ValueError("这类文件还读不了：%s（可以传 Word、PDF、Excel、PPT、文本、图片）" % (ext or name))


def ocr_image(data, ext):
    env = {}
    for line in open("/opt/cligw/.env", encoding="utf-8"):
        if "=" in line and not line.startswith("#"): k, v = line.strip().split("=", 1); env[k] = v.strip('"')
    mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
    body = {"model": "gpt-6-astra", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "把图片里的文字原样提取出来，保持段落和表格的行列；看不清的写[看不清]，不要补充解释。"},
        {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())}}]}]}
    req = urllib.request.Request("http://127.0.0.1:5012/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + env.get("CLIGW_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def _lark(args, timeout=180):
    r = subprocess.run(["lark-cli"] + args + ["--as", "user"], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "").strip()
    try: j = json.loads(out)
    except Exception: j = None
    if r.returncode != 0 or (isinstance(j, dict) and j.get("ok") is False):
        msg = (j or {}).get("error") if isinstance(j, dict) else None
        raise ValueError("飞书没读到：%s" % (json.dumps(msg, ensure_ascii=False)[:160] if msg else (r.stderr or out)[-160:]))
    return j if j is not None else out


def _find_text(j):
    """lark-cli 的 JSON 里找正文（markdown / content / csv 字段）。"""
    if isinstance(j, str): return j
    if isinstance(j, dict):
        for k in ("markdown", "content", "csv", "text"):
            if isinstance(j.get(k), str) and j[k].strip(): return j[k]
        for v in j.values():
            t = _find_text(v)
            if t: return t
    if isinstance(j, list):
        return "\n".join(t for t in (_find_text(x) for x in j) if t)
    return ""


def _sheets(j):
    out = []
    def walk(x):
        if isinstance(x, dict):
            sid = x.get("sheet_id") or x.get("reference_id")
            if sid and (x.get("title") or x.get("name")): out.append((sid, x.get("title") or x.get("name")))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(j); seen = set()
    return [s for s in out if not (s[0] in seen or seen.add(s[0]))]


def parse_link(url):
    u = url.strip()
    if not re.match(r"^https?://", u): raise ValueError("链接要以 http 开头")
    if re.search(r"\.(feishu|larksuite)\.(cn|com)/", u):
        if "/base/" in u: raise ValueError("多维表格暂时读不了，导出成 Excel 再传")
        if "/sheets/" in u:
            info = _lark(["sheets", "+workbook-info", "--url", u])
            parts = []
            for sid, title in _sheets(info)[:10]:
                t = _find_text(_lark(["sheets", "+csv-get", "--url", u, "--sheet-id", sid, "--max-chars", "60000"]))
                if t.strip(): parts.append("【表：%s】\n%s" % (title, t))
            if not parts: raise ValueError("表格是空的，或没有读取权限")
            return "\n\n".join(parts)
        t = _find_text(_lark(["docs", "+fetch", "--doc", u, "--doc-format", "markdown"]))
        if not t.strip(): raise ValueError("文档是空的，或没有读取权限")
        return t
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def add(project, name, text, kind, material_path):
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())[:MAX]
    if len(text) < 10: raise ValueError("没读出有用的文字")
    stamp = time.strftime("%Y-%m-%d %H:%M")
    with open(material_path, "a", encoding="utf-8") as f:
        f.write("\n\n## 来自：%s（%s，%s 上传）\n%s\n" % (name, kind, stamp, text))
    sp = os.path.join(WORK, "%s_sources.json" % project)
    try: src = json.load(open(sp, encoding="utf-8"))
    except Exception: src = []
    src.append({"name": name, "kind": kind, "chars": len(text), "at": stamp, "preview": text[:120]})
    json.dump(src, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"name": name, "kind": kind, "chars": len(text), "preview": text[:200], "sources": src}


def keep_original(project, name, data):
    d = os.path.join(UP, project); os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^\w.\-一-鿿]", "_", name)[-80:] or "file"
    open(os.path.join(d, time.strftime("%Y%m%d%H%M%S-") + safe), "wb").write(data)
