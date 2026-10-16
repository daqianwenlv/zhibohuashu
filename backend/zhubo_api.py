# 这是什么：直播话术页 /workspace/zhubo/ 的后端接口，从线上 y1y1:/opt/ai-office/auth_server.py 里摘出的 zhubo 相关部分（只读参考）
# 谁用：看后端怎么配音、预生成、上传真人录音；线上真正运行的是 auth_server.py（端口 5080，nginx 把 /workspace/api/zhubo/ 转过去）
# 什么时候改：auth_server.py 里 zb_* 函数或 /api/zhubo/* 路由改了，就重新摘一遍同步过来
import hashlib, json, os, re, subprocess, threading, time, urllib.request

# ===== 工具函数（auth_server.py 原样摘录）=====
VOE = "http://127.0.0.1:5072"
ZB_AUDIO = "/var/www/y1-home/workspace/zhubo/audio"
_tts_lock = threading.Lock(); _tts_busy = set()
def voe_req(method, path, body=None, timeout=30, raw=False):
    tok = open("/opt/voe/token.txt").read().strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(VOE + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read() if raw else json.load(r)
def zb_voices():
    d = voe_req("GET", "/api/v1/samples")
    items = d.get("samples", d) if isinstance(d, dict) else d
    return [{"id": x.get("id"), "name": x.get("name"), "who": ((x.get("scene") or {}).get("who") or "")[:40]}
            for x in items if x.get("name") and re.match(r"^[0-9a-f]{12}$", str(x.get("id") or "")) and not re.match(r"^[0-9a-f]{12,}$", x.get("name"))]
def zb_tts(text, voice):
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:1500]
    if len(text) < 2: raise ValueError("没有可读的台词")
    if not re.match(r"^[0-9a-f]{12}$", voice or ""): raise ValueError("声音不对")
    key = hashlib.sha1((voice + "|" + text).encode()).hexdigest()[:20]
    f = os.path.join(ZB_AUDIO, key + ".mp3")
    if os.path.isfile(f): return {"url": "audio/%s.mp3" % key, "cached": True}
    with _tts_lock:
        if key in _tts_busy: raise RuntimeError("这一段正在生成，稍等再点")
        _tts_busy.add(key)
    try:
        meta = voe_req("POST", "/api/v1/generate", {"text": text, "samples": [voice], "format": "mp3"}, timeout=300)
        url = str(meta.get("audio_url") or "")
        m = re.match(r"^out/([0-9a-f]{16})\.mp3$", url)
        if not m: raise RuntimeError("声音工作台没有返回音频")
        audio = voe_req("GET", "/out/%s.mp3" % m.group(1), timeout=60, raw=True)
        os.makedirs(ZB_AUDIO, exist_ok=True)
        tmp = f + ".tmp"
        open(tmp, "wb").write(audio); os.replace(tmp, f); os.chmod(f, 0o644)
        return {"url": "audio/%s.mp3" % key, "cached": False, "seconds": meta.get("duration")}
    finally:
        with _tts_lock: _tts_busy.discard(key)

def zb_norm(t): return re.sub(r"\s+", " ", str(t or "")).strip()[:1500]
def zb_rec_key(text): return "rec-" + hashlib.sha1(zb_norm(text).encode()).hexdigest()[:20]
def zb_tts_key(voice, text): return hashlib.sha1((voice + "|" + zb_norm(text)).encode()).hexdigest()[:20]
def zb_have(voice, texts):
    out = []
    for t in (texts or [])[:400]:
        r = zb_rec_key(t)
        if os.path.isfile(os.path.join(ZB_AUDIO, r + ".mp3")): out.append({"url": "audio/%s.mp3" % r, "rec": True}); continue
        k = zb_tts_key(voice, t)
        out.append({"url": "audio/%s.mp3" % k, "rec": False} if os.path.isfile(os.path.join(ZB_AUDIO, k + ".mp3")) else None)
    return out
def zb_upload(text, data):
    if len(zb_norm(text)) < 2: raise ValueError("没有对应的台词")
    if len(data) < 1000: raise ValueError("音频太短")
    os.makedirs(ZB_AUDIO, exist_ok=True)
    key = zb_rec_key(text); src = os.path.join(ZB_AUDIO, key + ".upload"); dst = os.path.join(ZB_AUDIO, key + ".mp3")
    open(src, "wb").write(data)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k", dst + ".tmp.mp3"], capture_output=True, text=True, timeout=120)
    os.remove(src)
    if r.returncode != 0: raise ValueError("这个文件读不出声音，换 mp3、m4a 或 wav 试试")
    os.replace(dst + ".tmp.mp3", dst); os.chmod(dst, 0o644)
    return {"url": "audio/%s.mp3" % key, "rec": True}
def zb_unrec(text):
    f = os.path.join(ZB_AUDIO, zb_rec_key(text) + ".mp3")
    if os.path.isfile(f): os.replace(f, f + ".removed")
    return {"ok": True}
ZB_DATA = "/var/www/y1-home/workspace/zhubo/data"
_pregen = {}
def zb_texts(project):
    d = json.load(open(os.path.join(ZB_DATA, re.sub(r"[^\w-]", "", project) + ".json"), encoding="utf-8"))
    t = [v.get("host") for sc in d.get("scenes", []) for v in sc.get("versions", [])]          # 场景优先：主播最常用
    segs = (d.get("script") or {}).get("segments", [])
    t += [g.get("host") for g in segs] + [g.get("host_b") for g in segs if g.get("host_b")]
    t += ["\n".join(x for x in (p.get("hook"), p.get("picture"), p.get("price_line"), p.get("push")) if x) for p in d.get("products", [])]
    seen, out = set(), []
    for x in t:
        n = zb_norm(x)
        if len(n) >= 2 and n not in seen: seen.add(n); out.append(n)
    return out
def zb_pregen_start(project, voice, texts=None):
    key = project + "|" + voice
    st = _pregen.get(key)
    if st and st.get("running"): return st
    # 页面会把改过之后的台词（含自己加的、AI 现场补的）一起传上来；没传就按生成稿
    if texts: texts = list(dict.fromkeys(n for n in (zb_norm(x) for x in texts[:400] if isinstance(x, str)) if len(n) >= 2))
    else: texts = zb_texts(project)
    st = {"running": True, "total": len(texts), "done": sum(1 for x in zb_have(voice, texts) if x), "failed": 0, "started": time.strftime("%H:%M")}
    _pregen[key] = st
    def work(q):
        while True:
            with _tts_lock:
                if not q: return
                t = q.pop(0)
            if zb_have(voice, [t])[0]: continue
            try: zb_tts(t, voice); st["done"] += 1
            except Exception: st["failed"] += 1
    q = [t for t in texts if not zb_have(voice, [t])[0]]
    ths = [threading.Thread(target=work, args=(q,), daemon=True) for _ in range(2)]
    def watch():
        for th in ths: th.start()
        for th in ths: th.join()
        st["running"] = False; st["finished"] = time.strftime("%H:%M")
    threading.Thread(target=watch, daemon=True).start()
    return st

# ===== 新增：自己改的台词 / 快捷键 / 自填资料，AI 现场补一段（这几段要合进 auth_server.py）=====
ZB_WORK = "/opt/ai-office/zhubo/data"   # 不在网站目录下：改动和自填资料只走接口读写
def zb_mine_path(project):
    pj = re.sub(r"[^\w-]", "", str(project or ""))
    if not re.match(r"^[\w-]{2,40}$", pj): raise ValueError("项目不对")
    return os.path.join(ZB_WORK, pj + "_mine.json")
def zb_mine_get(project):
    f = zb_mine_path(project)
    if not os.path.isfile(f): return {}
    return json.load(open(f, encoding="utf-8"))
def zb_mine_put(project, data, who=""):
    if not isinstance(data, dict): raise ValueError("格式不对")
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) > 2 * 1024 * 1024: raise ValueError("内容太多了")
    f = zb_mine_path(project); os.makedirs(ZB_WORK, exist_ok=True)
    data["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S"); data["saved_by"] = who
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp: json.dump(data, fp, ensure_ascii=False)
    os.replace(tmp, f)
    return {"ok": True, "saved_at": data["saved_at"]}
def zb_gen(req):
    # 单段生成交给 gen.py --one（和整场生成同一套技能、资料与口吻），这里只转一手
    if not isinstance(req, dict) or not re.match(r"^[\w-]{2,40}$", str(req.get("project") or "")): raise ValueError("参数不对")
    if req.get("kind") == "faq" and len(str(req.get("ask") or "").strip()) < 2: raise ValueError("先写观众问了什么")
    r = subprocess.run(["python3", "/opt/ai-office/zhubo/gen.py", "--one"], input=json.dumps(req, ensure_ascii=False),
                       capture_output=True, text=True, timeout=240, cwd="/opt/ai-office/zhubo")
    if r.returncode != 0: raise RuntimeError((r.stderr.strip().splitlines() or ["没写出来"])[-1][:120])
    out = json.loads(r.stdout.strip().splitlines()[-1])
    if not str(out.get("text") or out.get("a") or "").strip(): raise RuntimeError("没写出来，再点一次")
    return out


# ===== 路由（auth_server.py 中 Handler.do_GET / do_POST 的 zhubo 分支，原样摘录）=====
#         if p == "/api/zhubo/pregen":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
#             st = _pregen.get((q.get("project") or [""])[0] + "|" + (q.get("voice") or [""])[0])
#             return self._send(200, st or {"running": False})
#         if p == "/api/zhubo/mine":   # 新增
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
#             try: return self._send(200, {"mine": zb_mine_get((q.get("project") or [""])[0])})
#             except ValueError as e: return self._send(422, {"error": str(e)})
#         if p == "/api/zhubo/voices":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try: return self._send(200, {"voices": zb_voices(), "default": "4188dc46e3fd"})
#             except Exception as e: return self._send(502, {"error": "声音工作台暂时连不上"})
#         if urllib.parse.urlparse(self.path).path == "/api/zhubo/upload":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             n = int(self.headers.get("Content-Length") or 0)
#             if n <= 0 or n > 30 * 1024 * 1024: return self._send(413, {"error": "文件太大，30MB 以内"})
#             data = self.rfile.read(n)
#             try: text = base64.b64decode(self.headers.get("X-Text-B64") or "").decode("utf-8")
#             except Exception: text = ""
#             try: return self._send(200, zb_upload(text, data))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception: return self._send(500, {"error": "上传没成功"})
#         if p == "/api/zhubo/have":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             return self._send(200, {"have": zb_have(str(body.get("voice") or ""), body.get("texts") or [])})
#         if p == "/api/zhubo/unrec":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             return self._send(200, zb_unrec(body.get("text")))
#         if p == "/api/zhubo/pregen":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             v = str(body.get("voice") or ""); pj = str(body.get("project") or "")
#             if not re.match(r"^[0-9a-f]{12}$", v) or not re.match(r"^[\w-]{2,40}$", pj): return self._send(422, {"error": "参数不对"})
#             try: return self._send(200, zb_pregen_start(pj, v, body.get("texts") if isinstance(body.get("texts"), list) else None))
#             except FileNotFoundError: return self._send(404, {"error": "这个项目还没有话术"})
#         if p == "/api/zhubo/mine":   # 新增：存自己改的台词、快捷键、自填资料
#             u = self._user()
#             if not u: return self._send(401, {"error": "未登录"})
#             try: return self._send(200, zb_mine_put(body.get("project"), body.get("mine"), str(u.get("name") if isinstance(u, dict) else u)[:40]))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#         if p == "/api/zhubo/gen":    # 新增：AI 现场补一段（再写一版 / 回答评论区问题）
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try: return self._send(200, zb_gen(body))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(502, {"error": str(e)[:120] or "没写出来"})
#         if p == "/api/zhubo/tts":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try: return self._send(200, zb_tts(body.get("text"), str(body.get("voice") or "")))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(502, {"error": str(e)[:120] or "生成失败"})
