# 这是什么：直播话术页 /workspace/zhubo/ 的后端接口，从线上 y1y1:/opt/ai-office/auth_server.py 里摘出的 zhubo 相关部分（只读参考）
# 谁用：看后端怎么配音、预生成、上传真人录音；线上真正运行的是 auth_server.py（端口 5080，nginx 把 /workspace/api/zhubo/ 转过去）
# 什么时候改：auth_server.py 里 zb_* 函数或 /api/zhubo/* 路由改了，就重新摘一遍同步过来
import hashlib, json, os, re, subprocess, sys, threading, time, urllib.request

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
ZB_HOSTS = "/var/www/y1-home/workspace/zhubo/data/hosts.json"
ZB_HOSTS_DEFAULT = [{"id": "9c685d238b8a", "name": "小艺", "rate": 15, "speed": 1.0}, {"id": "4188dc46e3fd", "name": "小兔", "rate": 15, "speed": 1.0}]
def zb_hosts():
    try: h = json.load(open(ZB_HOSTS, encoding="utf-8"))
    except Exception: h = None
    return h if isinstance(h, list) and h else [dict(x) for x in ZB_HOSTS_DEFAULT]
def zb_rate(voice):
    return int(next((h.get("rate", 15) for h in zb_hosts() if h.get("id") == voice), 15))
def zb_tts(text, voice):
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:1500]
    if len(text) < 2: raise ValueError("没有可读的台词")
    if not re.match(r"^[0-9a-f]{12}$", voice or ""): raise ValueError("声音不对")
    rate = zb_rate(voice)
    key = zb_tts_key(voice, text)
    f = os.path.join(ZB_AUDIO, key + ".mp3")
    if os.path.isfile(f): return {"url": "audio/%s.mp3" % key, "cached": True}
    with _tts_lock:
        if key in _tts_busy: raise RuntimeError("这一段正在生成，稍等再点")
        _tts_busy.add(key)
    try:
        meta = voe_req("POST", "/api/v1/generate", {"text": text, "samples": [voice], "format": "mp3", "speech_rate": rate}, timeout=300)
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
def zb_tts_key(voice, text):
    r = zb_rate(voice)
    return hashlib.sha1(((voice + "|" + zb_norm(text)) if r == 15 else (voice + "|r%d|" % r + zb_norm(text))).encode()).hexdigest()[:20]
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
sys.path.insert(0, "/opt/ai-office/zhubo")
import lib as ZL
import ingest as ZI
ZB_WORK = "/opt/ai-office/zhubo/data"
def zb_pid(x):
    x = str(x or "")
    if not re.match(r"^[\w-]{2,40}$", x): raise ValueError("项目不对")
    return x
def zb_material_path(project, write=False):
    own = os.path.join(ZB_WORK, "%s_material.md" % project)
    if write or os.path.isfile(own): return own
    old = os.path.join(ZB_WORK, "%s_material.md" % project.split("-")[0])
    return old if os.path.isfile(old) else own
def zb_gen_status(project):
    try: return json.load(open(os.path.join(ZB_WORK, "%s.gen.json" % project), encoding="utf-8"))
    except Exception: return {"running": False}
def zb_gen_start(project, scene):
    st = zb_gen_status(project)
    if st.get("running"): return st
    if scene and scene not in ZL.KEYS: raise ValueError("没有这个场景")
    subprocess.Popen(["python3", "/opt/ai-office/zhubo/gen_lib.py", "--project", project] + (["--scene", scene] if scene else []),
                     cwd="/opt/ai-office/zhubo", stdout=open(os.path.join(ZB_WORK, "%s.gen.log" % project), "a"), stderr=subprocess.STDOUT, start_new_session=True)
    return {"running": True, "scene": scene or "全部", "started": time.strftime("%H:%M")}
def zb_edit_item(project, iid, text, title):
    lb = ZL.load(project)
    if not lb: raise ValueError("这个项目还没有话术库")
    it = next((i for _, i in ZL.all_items(lb) if i["id"] == iid), None)
    if not it: raise ValueError("没有这条话术")
    text = str(text or "").strip()
    if len(text) < 2: raise ValueError("话术不能为空")
    it["text"] = text[:1500]
    if title is not None and str(title).strip(): it["title"] = str(title).strip()[:24]
    it["edited"] = True; it["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
    ZL.save(project, lb); return it
def zb_add_item(project, scene, title, text):
    lb = ZL.load(project)
    if not lb: raise ValueError("这个项目还没有话术库")
    sc = next((x for x in lb["scenes"] if x["key"] == scene), None)
    if not sc: raise ValueError("没有这个场景")
    n = max([int(i["id"].rsplit("-", 1)[1]) for i in sc["items"]] + [0]) + 1
    it = {"id": "%s-%d" % (scene, n), "title": (str(title or "").strip() or "%s %d" % (sc["name"], n))[:24], "text": str(text or "").strip()[:1500],
          "src": [], "edited": True, "edited_at": time.strftime("%Y-%m-%d %H:%M")}
    if len(it["text"]) < 2: raise ValueError("话术不能为空")
    sc["items"].append(it); ZL.save(project, lb); return it
def zb_del_item(project, iid):
    lb = ZL.load(project)
    for sc in lb["scenes"]:
        sc["items"] = [i for i in sc["items"] if i["id"] != iid]
    lb["hotkeys"] = [h for h in lb.get("hotkeys", []) if h != iid]
    ZL.save(project, lb); return {"ok": True}
def zb_set_hotkeys(project, keys):
    lb = ZL.load(project)
    ids = {i["id"] for _, i in ZL.all_items(lb)}
    lb["hotkeys"] = [k for k in (keys or []) if k in ids][:9]
    ZL.save(project, lb); return {"hotkeys": lb["hotkeys"]}
def zb_hosts_view():
    hs = zb_hosts(); vs = {}
    try:
        d = voe_req("GET", "/api/v1/samples"); items = d.get("samples", d) if isinstance(d, dict) else d
        vs = {x.get("id"): x for x in items}
    except Exception: pass
    out = []
    for h in hs:
        v = vs.get(h["id"]) or {}; sc = v.get("scene") or {}
        out.append(dict(h, name=v.get("name") or h.get("name"), who=sc.get("who", ""), where=sc.get("where", ""), mood=sc.get("mood", "")))
    others = [{"id": k, "name": x.get("name"), "who": ((x.get("scene") or {}).get("who") or "")[:40]} for k, x in vs.items()
              if k not in {h["id"] for h in hs} and x.get("name") and not re.match(r"^[0-9a-f]{12,}$", x.get("name"))]
    return {"hosts": out, "voices": others}
def zb_save_hosts(items):
    vs = {}
    try:
        d = voe_req("GET", "/api/v1/samples"); vs = {x.get("id"): x for x in (d.get("samples", d) if isinstance(d, dict) else d)}
    except Exception: pass
    out = []
    for h in (items or [])[:12]:
        vid = str(h.get("id") or "")
        if vid not in vs: continue
        out.append({"id": vid, "name": vs[vid].get("name"), "rate": max(-20, min(80, int(h.get("rate", 15)))), "speed": max(0.8, min(2.0, round(float(h.get("speed", 1.0)), 2)))})
    if not out: raise ValueError("至少留一位主播")
    tmp = ZB_HOSTS + ".tmp"; json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, ZB_HOSTS)
    return zb_hosts_view()
def zb_host_scene(vid, name, who, where, mood):
    if not re.match(r"^[0-9a-f]{12}$", vid or ""): raise ValueError("主播不对")
    body = {"scene": {"who": str(who or "")[:200], "where": str(where or "")[:200], "mood": str(mood or "")[:200]}}
    if name and str(name).strip(): body["name"] = str(name).strip()[:20]
    voe_req("POST", "/api/v1/samples/%s" % vid, body)
    return zb_hosts_view()
def zb_host_upload(name, data):
    name = str(name or "").strip()[:20]
    if not name: raise ValueError("先写主播名字")
    if len(data) < 5000: raise ValueError("录音太短，录 10 到 30 秒")
    tok = open("/opt/voe/token.txt").read().strip()
    req = urllib.request.Request(VOE + "/api/v1/samples?" + urllib.parse.urlencode({"name": name, "note": "直播话术录入"}), data=data, method="POST",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=120) as r: d = json.load(r)
    vid = d.get("id") or (d.get("sample") or {}).get("id")
    if not vid: raise ValueError("声音工作台没收下这段录音")
    hs = zb_hosts(); hs.append({"id": vid, "name": name, "rate": 15, "speed": 1.0})
    tmp = ZB_HOSTS + ".tmp"; json.dump(hs, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, ZB_HOSTS)
    return zb_hosts_view()
_pregen = {}
def zb_texts(project):
    lb = ZL.load(project)
    if lb:
        seen, out = set(), []
        for _, it in ZL.all_items(lb):
            n = zb_norm(it.get("text"))
            if len(n) >= 2 and n not in seen: seen.add(n); out.append(n)
        return out
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
def zb_pregen_start(project, voice):
    key = project + "|" + voice
    st = _pregen.get(key)
    if st and st.get("running"): return st
    texts = zb_texts(project)
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

# ===== 路由（auth_server.py 中 Handler.do_GET / do_POST 的 zhubo 分支，原样摘录）=====
#         if p == "/api/zhubo/pregen":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
#             st = _pregen.get((q.get("project") or [""])[0] + "|" + (q.get("voice") or [""])[0])
#             return self._send(200, st or {"running": False})
#         if p in ("/api/zhubo/gen", "/api/zhubo/material", "/api/zhubo/hosts"):
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
#             try:
#                 if p == "/api/zhubo/hosts": return self._send(200, zb_hosts_view())
#                 pj = zb_pid((q.get("project") or [""])[0])
#                 if p == "/api/zhubo/gen": return self._send(200, zb_gen_status(pj))
#                 f = zb_material_path(pj)
#                 try: srcs = json.load(open(os.path.join(ZB_WORK, "%s_sources.json" % pj), encoding="utf-8"))
#                 except Exception: srcs = []
#                 txt = open(f, encoding="utf-8").read() if os.path.isfile(f) else ""
#                 txt = re.sub(r"\A(?:\s*<!--.*?-->\s*\n)+", "", txt, flags=re.S)
#                 return self._send(200, {"text": txt, "sources": srcs})
#             except ValueError as e: return self._send(422, {"error": str(e)})
#         if p == "/api/zhubo/voices":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try: return self._send(200, {"voices": zb_voices(), "default": "4188dc46e3fd"})
#             except Exception as e: return self._send(502, {"error": "声音工作台暂时连不上"})
#         if urllib.parse.urlparse(self.path).path == "/api/zhubo/host-upload":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             n = int(self.headers.get("Content-Length") or 0)
#             if n <= 0 or n > 30 * 1024 * 1024: return self._send(413, {"error": "文件太大，30MB 以内"})
#             data = self.rfile.read(n)
#             name = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("name", [""])[0]
#             try: return self._send(200, zb_host_upload(name, data))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception: return self._send(502, {"error": "声音工作台暂时连不上"})
#         if urllib.parse.urlparse(self.path).path == "/api/zhubo/material-file":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             n = int(self.headers.get("Content-Length") or 0)
#             if n <= 0 or n > 40 * 1024 * 1024: return self._send(413, {"error": "文件太大，40MB 以内"})
#             data = self.rfile.read(n)
#             q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
#             try:
#                 pj = zb_pid((q.get("project") or [""])[0]); name = (q.get("name") or ["文件"])[0][:120]
#                 ZI.keep_original(pj, name, data)
#                 return self._send(200, ZI.add(pj, name, ZI.parse_file(name, data), "文件", zb_material_path(pj)))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(500, {"error": "没解析出来：%s" % str(e)[:100]})
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
#         if p == "/api/zhubo/material-link":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try:
#                 pj = zb_pid(body.get("project")); url = str(body.get("url") or "").strip()
#                 kind = "飞书" if re.search(r"feishu|larksuite", url) else "网页"
#                 return self._send(200, ZI.add(pj, url[:120], ZI.parse_link(url), kind, zb_material_path(pj)))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(500, {"error": "没读出来：%s" % str(e)[:100]})
#         if p in ("/api/zhubo/gen", "/api/zhubo/item", "/api/zhubo/item-add", "/api/zhubo/item-del", "/api/zhubo/hotkeys", "/api/zhubo/material", "/api/zhubo/hosts", "/api/zhubo/host-scene"):
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try:
#                 if p == "/api/zhubo/hosts": return self._send(200, zb_save_hosts(body.get("hosts")))
#                 if p == "/api/zhubo/host-scene": return self._send(200, zb_host_scene(str(body.get("id") or ""), body.get("name"), body.get("who"), body.get("where"), body.get("mood")))
#                 pj = zb_pid(body.get("project"))
#                 if p == "/api/zhubo/gen": return self._send(200, zb_gen_start(pj, str(body.get("scene") or "")))
#                 if p == "/api/zhubo/item": return self._send(200, zb_edit_item(pj, str(body.get("id") or ""), body.get("text"), body.get("title")))
#                 if p == "/api/zhubo/item-add": return self._send(200, zb_add_item(pj, str(body.get("scene") or ""), body.get("title"), body.get("text")))
#                 if p == "/api/zhubo/item-del": return self._send(200, zb_del_item(pj, str(body.get("id") or "")))
#                 if p == "/api/zhubo/hotkeys": return self._send(200, zb_set_hotkeys(pj, body.get("keys")))
#                 f = zb_material_path(pj, write=True); text = str(body.get("text") or "")[:60000]
#                 if os.path.isfile(f): os.replace(f, f + ".bak-" + time.strftime("%Y%m%d%H%M%S"))
#                 hdr = "<!-- 这是什么：%s 的景区资料（直播话术页「资料」里编辑或上传，%s 保存） -->\n<!-- 谁用：/opt/ai-office/zhubo/gen_lib.py 生成话术时读取 -->\n<!-- 什么时候改：在直播话术页「资料」里改，不要直接改文件 -->\n" % (pj, time.strftime("%Y-%m-%d %H:%M"))
#                 open(f, "w", encoding="utf-8").write(hdr + re.sub(r"\A(?:\s*<!--.*?-->\s*\n)+", "", text, flags=re.S)); return self._send(200, {"ok": True, "saved_at": time.strftime("%H:%M")})
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(502, {"error": str(e)[:120] or "没保存成功"})
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
#             try: return self._send(200, zb_pregen_start(pj, v))
#             except FileNotFoundError: return self._send(404, {"error": "这个项目还没有话术"})
#         if p == "/api/zhubo/tts":
#             if not self._user(): return self._send(401, {"error": "未登录"})
#             try: return self._send(200, zb_tts(body.get("text"), str(body.get("voice") or "")))
#             except ValueError as e: return self._send(422, {"error": str(e)})
#             except Exception as e: return self._send(502, {"error": str(e)[:120] or "生成失败"})
