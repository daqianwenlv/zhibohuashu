#!/usr/bin/env python3
# 这是什么：直播话术生成——读项目在售商品（来客实时）、项目档案（活动、打法、经营建议）、知识库平台规则，按「直播话术」技能写出场景话术、产品话术与整场脚本，存成页面读的 JSON
# 谁用：y1y1 上 python3 /opt/ai-office/zhubo/gen.py --project yaoxue-ice-world [--format 日播]；页面 /workspace/zhubo/ 读 data/<项目>.json
#       页面上「AI 再写一版」「评论区问题 AI 回答」走 --one：后端把请求 JSON 从 stdin 传进来，stdout 只出一行结果 JSON
# 什么时候改：话术技能结构变了、页面要的字段变了
import argparse, json, os, re, subprocess, sys, time
WS = "/var/www/y1-home/workspace"
HX = "/opt/ai-office/huanxin"
OUT = WS + "/zhubo/data"
WORK = "/opt/ai-office/zhubo/data"

def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def skill_text():
    base = WS + "/skills/zhibo-huashu"; parts = [open(base + "/SKILL.md", encoding="utf-8").read()]
    for f in sorted(os.listdir(base + "/references")):
        parts.append("\n\n===== 附件 references/%s =====\n" % f + open(base + "/references/" + f, encoding="utf-8").read())
    q = WS + "/jingyan/quanju.md"
    if os.path.isfile(q): parts.append("\n\n===== 全局口径 =====\n" + open(q, encoding="utf-8").read())
    return "".join(parts)

def mine(pid):
    # 页面上自己改过、自己填的东西（台词修改、快捷键、自己填的景区资料），后端 /api/zhubo/mine 存在这里
    return load(WORK + "/%s_mine.json" % pid, {}) or {}

def doc_of(pid):
    mp = WORK + "/%s_material.md" % pid.split("-")[0]
    return open(mp, encoding="utf-8").read() if os.path.isfile(mp) else ""

def own_of(pid):
    own = str(mine(pid).get("material") or "").strip()
    return ("<景区资料 项目方在话术页自己填的，可以直接用，出处写「资料:自填」>\n%s\n</景区资料>\n\n" % own) if own else ""

def engine_run(prompt, log):
    sys.path.insert(0, HX)
    for line in open(HX + "/.env", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); os.environ.setdefault(k, v)
    from app import engine
    engine.SYSTEM_GUARD = "【运行环境】无人值守批处理：不要读写文件、不要执行命令；只依据下面给出的材料写，材料里没有的不编。"
    return engine.run(prompt, log, out={}, use_mcp=False)

# 主播口吻：配音念出来容易慢、平，所以台词本身要写得快、短、有劲
VOICE = ("写法要求：像真主播在镜头前说话——口语、短句、有画面、有节奏和情绪，能直接念；不要写成说明书（不说「商品售价是」，说「今天这张 1699」）。"
         "这些台词会直接转成配音播放，句子要短（一句尽量不超过 15 个字）、多用感叹和催促（「家人们」「赶紧」「冲」），读出来要快、要带劲，不要拖腔和长定语。")

def card_brief(pid):
    c = load(HX + "/data/cards/%s.json" % pid, {}) or {}
    month = time.strftime("%Y-%m")
    return {"项目": c.get("name"), "客户": c.get("客户"), "大千项目号": c.get("daqian_project_id"),
            "本月方针": (c.get("方针按月") or {}).get(month), "本月节奏": (c.get("本月节奏") or {}).get(month),
            "已定事项": [x.get("text") for x in c.get("已定事项", []) if x.get("status") == "open"][-10:],
            "经营建议": [x.get("text") for x in c.get("经营建议", [])[-8:]],
            "打法档案": [{k: x.get(k) for k in ("打法", "结果", "证据", "可复用条件")} for x in c.get("打法档案", [])[-10:]],
            "口径": c.get("口径")}

SCHEMA = """只输出一个 JSON 对象，不要任何其他文字，结构如下（所有文本用主播能直接说出口的中文口语；src 写出处，只能是：商品:<商品ID> / 档案:<条目> / 规则:<文档名> / 技能:<编号>）：
{
 "summary": "一句话：这一场主打什么、为什么",
 "lineup": [{"product_id":"", "role":"主推|引流|搭配|不推", "why":"一句话理由（能指到出处）"}],   // 覆盖全部在售商品
 "products": [   // 只写 role 为 主推/引流/搭配 的商品，最多 8 个
   {"product_id":"", "short":"口播用的短名（≤12 字）", "hook":"一句话卖点", "picture":"体验画面（2–3 句）", "includes":"包含什么（口语）",
    "price_line":"价格怎么说（只说商品里的售价，不说原价/最低价）", "for_whom":"适合谁", "must_say":["必须讲清的须知（实名、陪同、有效期、不含项等）"],
    "push":"促单一句（只用真实的期限、库存说法）", "faq":[{"q":"","a":""}], "src":["商品:..."]}
 ],
 "scenes": [   // 11 个直播场景，按这个顺序：开场、讲景区、过品、留人互动、讲品、促单、福利说明、答疑承接、冷场救场、质疑与差评、下播预告
   {"key":"opening|venue|walkthrough|retain|pitch|close|perks|qa|cold|objection|ending", "name":"", "when":"什么时候用（一句）",
    "versions":[{"style":"这一版的风格，两到四个字，按场景自己定，版本间要真的不同", "host":"主播台词"}],   // 每个场景 3 个版本
    "src":["..."]}
 ],
 "quick_comments": [{"q":"观众常问","a":"主播口头回答（能直接念、会转成配音，2–4 句）"}],   // 10–15 条，覆盖价格、怎么用、预约、退改、人数年龄、交通、营业时间、含不含什么
 "script": {"format":"日播", "duration_min":120, "theme":"本场主题",
   "segments":[{"from":"00:00","to":"00:05","stage":"开场|讲景区|过品|讲品|留人|互动|福利|促单|答疑|预告","product_id":"可空","host":"主播台词（完整可念）","host_b":"备选版本（可空）","assistant":"小助手配合","control":"中控动作（上链接、切讲解、置顶话术等；没有就空）"}]},   // 覆盖 120 分钟，10–16 段，主推品至少讲两轮；开场之后紧跟一段 stage=讲景区（10–15 分钟，用景区资料里的面积、雪道、项目、演艺、周边），促单、答疑、留人或互动各至少一段
 "compliance": [{"rule":"Q1.1 价格表述", "ok":true, "note":"怎么做到的或哪里要人看"}],   // 按契约 Q1.1–Q1.6 逐条，外加知识库里与本场相关的规则
 "missing": ["缺的资料：景区故事、打卡点等，写清要什么、谁能给"],
 "doc_review": [{"module":"原稿的段落名", "kept":"保留了什么（结构、事实、说法）", "changes":[{"orig":"原句（原样摘）", "why":"为什么改（违反哪条）", "new":"改成什么"}]}],   // 有原话术稿时必填：逐段说明拆到哪些场景、改了哪些句子
 "verify": ["原稿里需要园方核实的事实（数字、设施、承诺），写清核实什么"]
}"""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--format", default="日播")
    o = ap.parse_args()
    card = card_brief(o.project)
    goods = load(WORK + "/%s_goods.json" % o.project.split("-")[0], None) or load(WORK + "/%s_goods.json" % o.project, None)
    if not goods or not goods.get("goods"):
        r = subprocess.run(["python3", "/opt/ai-office/ygc/caozuo.py", "goods", "--project", card["项目"]], capture_output=True, text=True, timeout=900, cwd="/opt/ai-office/ygc")
        goods = json.loads(r.stdout.strip().splitlines()[-1])
    kb = load(WORK + "/%s_kb.json" % o.project.split("-")[0], []) or []
    material = doc_of(o.project)
    prompt = ("你是大千文旅 AI 办公室的直播运营员，按下面的技能定义，为「%s」官方直播间写一场%s的话术。今天是 %s。\n"
              "三维融合：门店卖点（只能来自在售商品信息）× 景区知识（项目资料里没有就不编，列进 missing）× 当下活动（商品名里的活动、项目档案的节奏与经营建议）。\n"
              "称呼观众用「家人们 / 朋友们」，称呼负责人只用角色。不说「秒杀」除非商品是秒杀活动；不诱导互动；评论区不挂链接，只说「点下方小房子 / 购物车」。\n"
              "%s"
              "价格可以用商品里的数字做真实算术（如五次卡一次合多少、两人一晚合多少），算出来的数要准；开场按官方公式：打招呼＋我们是谁＋今天主题＋今天的好处＋互动引导＋全场快速过一遍。"
              "每个场景写 3 个版本，风格真的拉开（如：讲画面、讲划算、讲人群；或快节奏、慢节奏）。合规照样守住：不编造、不绝对化、须知讲清。\n\n"
              "<技能定义>\n%s\n</技能定义>\n\n<在售商品 来客实时读取于 %s>\n%s\n</在售商品>\n\n<项目档案>\n%s\n</项目档案>\n\n%s<平台规则摘录 知识库>\n%s\n</平台规则摘录>\n\n%s") % (
        card["项目"], o.format, time.strftime("%Y-%m-%d"), VOICE, skill_text(), goods.get("read_at"),
        json.dumps(goods.get("goods"), ensure_ascii=False, indent=0), json.dumps(card, ensure_ascii=False, indent=0),
        ((("<原话术稿 项目方提供，出处写「资料:原话术稿」>\n%s\n</原话术稿>\n"
         "以原话术稿为底：保留它的结构、口吻、节奏和信息量，景区事实（面积、雪道、项目、演艺、滴水湖、汤泉）可以直接用；"
         "但违规的必须改：极限词与贬低同行（天花板、吊打、封神、国内少见、别家不行）、原价与秒杀说法、和商品信息对不上的承诺（未用可退、随时预约、有效期超长、库存不多、错过再等一年）、"
         "诱导互动（扣1领福利这类）；原稿没有的要补上：每件在售商品怎么讲（价格、包含、须知）、答疑、冷场、质疑、下播、小助手配合。"
         "doc_review 逐段写清楚改了什么；verify 列出要园方核实的数。"
         "台词是主播当场说的话：出处只写进 src 字段，台词里绝不出现「原稿」「项目方」「资料显示」这类字眼；原稿里的数字和设施可以直接说，待核实的放进 verify。"
         "保留原稿的热情、画面感和节奏（感叹、短句、带人想象），只改掉违规的那几句，不要改得像说明书或免责声明，也不要用否定句吓人。"
         "整场脚本：开场后先用 10–15 分钟讲景区（园区、滑雪区、娱雪区、度假路线），再按商品讲；促单、互动、答疑各至少一段，结尾预告。\n\n") % material) if material else "") + own_of(o.project),
        "\n".join("《%s》%s" % (k.get("title"), k.get("text")) for k in kb[:14]), SCHEMA)
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)
    t0 = time.time()
    raw = engine_run(prompt, log)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0))
    gmap = {str(g.get("product_id")): g for g in goods.get("goods", [])}
    data["meta"] = {"project_id": o.project, "project": card["项目"], "client": card.get("客户"), "format": o.format,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M"), "goods_read_at": goods.get("read_at"), "seconds": int(time.time() - t0),
                    "sources": {"商品": len(gmap), "档案条目": len(card.get("经营建议") or []) + len(card.get("打法档案") or []), "规则文档": len({k.get("title") for k in kb})}}
    data["goods"] = {pid: {k: g.get(k) for k in ("name", "price_yuan", "use_window", "sold_window", "crowd", "refund", "limit", "stock", "state")} for pid, g in gmap.items()}
    data["kb"] = [{"title": k.get("title"), "doc_id": k.get("doc_id")} for k in kb]
    data["card"] = {"经营建议": card.get("经营建议"), "打法档案": card.get("打法档案"), "已定事项": card.get("已定事项")}
    os.makedirs(OUT, exist_ok=True)
    json.dump(data, open(OUT + "/%s.json" % o.project, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok", OUT + "/%s.json" % o.project, "用时 %ds" % (time.time() - t0))

ONE_KIND = {
    "scene": "为直播场景「{name}」（{when}）再写一版主播台词。已经有的版本：\n{have}\n新写的这一版要和已有版本明显不同。",
    "product": "为商品「{name}」再写一版讲品台词：一句卖点、体验画面、价格怎么说、促单收口，连成一段能直接念的话。已经有的版本：\n{have}\n新写的要明显不同。",
    "segment": "为整场脚本里 {name} 这一段（{when}）再写一版主播台词。已经有的版本：\n{have}\n新写的要明显不同。",
    "faq": "直播间评论区有观众问：「{ask}」。写主播当场口头回答这个问题的话（2–4 句，能直接念）。材料里查不到答案的不要编，就说「这个我让小助手马上帮您确认」并引导看商品详情页。",
}

def one():
    # 页面上的单段生成：读已生成的话术做上下文，只写一段，stdout 出一行 JSON
    req = json.load(sys.stdin)
    pid = re.sub(r"[^\w-]", "", str(req.get("project") or ""))
    kind = req.get("kind") if req.get("kind") in ONE_KIND else "scene"
    d = load(OUT + "/%s.json" % pid, {}) or {}
    if not d: raise SystemExit("这个项目还没有话术")
    card = card_brief(pid)
    have = "\n".join("- " + str(x)[:400] for x in (req.get("have") or [])[:6]) or "（还没有）"
    task = ONE_KIND[kind].format(name=str(req.get("name") or "")[:40], when=str(req.get("when") or "")[:80], have=have, ask=str(req.get("ask") or "")[:200])
    if kind != "faq" and str(req.get("ask") or "").strip(): task += "\n这次的要求：" + str(req.get("ask"))[:200]
    ctx = {"在售商品": d.get("goods"), "商品讲法": [{k: p.get(k) for k in ("product_id", "short", "hook", "includes", "price_line", "for_whom", "must_say", "faq")} for p in d.get("products", [])],
           "已有快捷回复": d.get("quick_comments")}
    out = '只输出一个 JSON 对象，不要任何其他文字：{"q":"把观众的问题整理成一句","a":"主播的回答"}' if kind == "faq" else '只输出一个 JSON 对象，不要任何其他文字：{"style":"这一版的风格，两到四个字","text":"主播台词"}'
    prompt = ("你是大千文旅 AI 办公室的直播运营员，在「%s」官方直播间直播中，现场补一段话术。今天是 %s。\n"
              "称呼观众用「家人们 / 朋友们」。不编造价格、库存、活动；不用绝对化用语；不说原价、最低价；评论区不挂链接，只说「点下方小房子 / 购物车」。%s\n\n"
              "<技能定义>\n%s\n</技能定义>\n\n<本场资料>\n%s\n</本场资料>\n\n<项目档案>\n%s\n</项目档案>\n\n%s\n\n任务：%s\n\n%s") % (
        card["项目"] or d.get("meta", {}).get("project"), time.strftime("%Y-%m-%d"), VOICE, skill_text(),
        json.dumps(ctx, ensure_ascii=False, indent=0), json.dumps(card, ensure_ascii=False, indent=0), own_of(pid) + doc_of(pid)[:12000], task, out)
    raw = engine_run(prompt, lambda m: print(time.strftime("%H:%M:%S"), m, file=sys.stderr, flush=True))
    m = re.search(r"\{.*\}", raw, re.S)
    r = json.loads(m.group(0))
    print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    if "--one" in sys.argv: one()
    else: main()
