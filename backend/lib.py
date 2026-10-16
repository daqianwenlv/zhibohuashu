# 这是什么：直播话术「话术库」的公共定义——场景表、库文件读写、旧版生成结果转成库、合并重新生成的结果（手改过的不覆盖）
# 谁用：/opt/ai-office/zhubo/gen.py（生成）、/opt/ai-office/auth_server.py（改话术、快捷键、资料）；库文件在 /var/www/y1-home/workspace/zhubo/data/<项目>.lib.json
# 什么时候改：场景增删、话术字段变了
import json, os, re, time, threading

DATA = "/var/www/y1-home/workspace/zhubo/data"
# (键, 主播叫法, 什么时候用, 生成几条)
SCENES = [
    ("opening", "开场", "刚开播、换一拨人进来时", "2–3 条"),
    ("venue", "讲景区", "介绍园区、玩法和周边", "3–5 条，按话题分：园区总览、滑雪、玩雪、度假路线等；每条都要讲出景区资料里的具体信息——面积、雪道等级与长度坡度、娱雪项目名字、演艺、周边位置，资料里有的数字直接说，带画面和热情"),
    ("pitch", "讲品", "讲某一件商品", "每件值得推的在售商品一条，最多 10 条"),
    ("close", "促单", "大家在犹豫、准备下单时", "3 条"),
    ("qa", "答疑", "回答评论区的问题", "至少 12 条，每条一个常见问题，标题写问题、正文写主播当场的回答"),
    ("retain", "留人", "人在走、要把人留住时", "3 条"),
    ("cold", "冷场救场", "没人说话、数据掉下来时", "3 条"),
    ("perks", "讲福利", "讲赠送、权益、套餐里多给的东西", "2–3 条"),
    ("walk", "过品", "快速把全场商品过一遍", "2 条"),
    ("objection", "有人质疑", "有人说贵、说假、说不好时", "3 条"),
    ("ending", "下播", "准备下播、预告下一场", "2 条"),
]
KEYS = [s[0] for s in SCENES]
_lock = threading.Lock()


def path(project):
    return os.path.join(DATA, re.sub(r"[^\w-]", "", project) + ".lib.json")


def load(project):
    try:
        return json.load(open(path(project), encoding="utf-8"))
    except Exception:
        return None


def save(project, lib):
    lib["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    p = path(project); tmp = p + ".tmp"
    with _lock:
        json.dump(lib, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, p); os.chmod(p, 0o644)


def all_items(lib):
    for sc in lib.get("scenes", []):
        for it in sc.get("items", []):
            yield sc, it


def numbered(lib):
    """全项目统一编号：按场景顺序、场景内顺序，从 1 开始。"""
    n, out = 0, {}
    for sc, it in all_items(lib):
        n += 1; out[it["id"]] = n
    return out


def blank_scenes():
    return [{"key": k, "name": n, "when": w, "items": []} for k, n, w, _ in SCENES]


def merge_scene(lib, key, new_items):
    """重新生成某个场景：手改过的条目原样保留，其余换成新写的；编号位置按 键-序号 稳定。"""
    sc = next(s for s in lib["scenes"] if s["key"] == key)
    kept = [it for it in sc["items"] if it.get("edited")]
    used = {it["id"] for it in kept}
    out, n = list(kept), 0
    for it in new_items:
        n += 1
        while "%s-%d" % (key, n) in used: n += 1
        out.append({"id": "%s-%d" % (key, n), "title": str(it.get("title") or "")[:24], "text": str(it.get("text") or ""),
                    "src": it.get("src") or [], "edited": False})
    sc["items"] = sorted(out, key=lambda x: int(x["id"].rsplit("-", 1)[1]))
    lib["hotkeys"] = [h for h in lib.get("hotkeys", []) if any(i["id"] == h for _, i in all_items(lib))]


def from_old(d):
    """把旧版生成结果（scenes 带版本、products、quick_comments）转成话术库。"""
    lib = {k: d.get(k) for k in ("meta", "summary", "goods", "kb", "card", "doc_review", "verify", "missing", "compliance", "lineup")}
    lib["scenes"] = blank_scenes()
    by = {s["key"]: s for s in lib["scenes"]}
    name2key = {"开场": "opening", "讲景区": "venue", "过品": "walk", "留人互动": "retain", "促单": "close", "福利说明": "perks",
                "答疑承接": "qa", "冷场救场": "cold", "质疑与差评": "objection", "下播预告": "ending"}
    for s in d.get("scenes", []):
        k = name2key.get(s.get("name"))
        if not k: continue
        for v in s.get("versions", []):
            by[k]["items"].append({"title": "", "text": v.get("host", ""), "src": s.get("src") or []})
    for p in d.get("products", []):
        by["pitch"]["items"].append({"title": p.get("short", ""), "src": p.get("src") or [],
                                     "text": "".join(x for x in (p.get("hook"), p.get("picture"), p.get("price_line"), p.get("push")) if x)})
    seen = set()
    qa = [(q.get("q"), q.get("a")) for q in d.get("quick_comments", [])] + [(f.get("q"), f.get("a")) for p in d.get("products", []) for f in p.get("faq", [])]
    for q, a in qa:
        if not q or q in seen: continue
        seen.add(q)
        by["qa"]["items"].append({"title": q.rstrip("？?"), "text": "有家人问%s%s" % (q if q.endswith(("？", "?")) else q + "？", a), "src": []})
    for s in lib["scenes"]:
        for i, it in enumerate(s["items"], 1):
            it.update(id="%s-%d" % (s["key"], i), edited=False)
            if not it["title"]: it["title"] = "%s %d" % (s["name"], i)
    ids = {it["id"] for _, it in all_items(lib)}
    lib["hotkeys"] = [x for x in ("opening-1", "close-1", "cold-1", "retain-1", "qa-1", "qa-2", "qa-3", "qa-4", "ending-1") if x in ids]
    return lib
