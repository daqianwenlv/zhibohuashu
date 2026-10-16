#!/usr/bin/env python3
# 这是什么：按场景生成直播话术库——读来客在售商品、景区资料、项目档案、平台规则，按「直播话术」技能写出各场景的编号话术，合并进 <项目>.lib.json（手改过的不覆盖）
# 谁用：工作台「生成话术」按钮经登录服务调用：python3 /opt/ai-office/zhubo/gen_lib.py --project yaoxue-ice-world [--scene qa]；状态写 /opt/ai-office/zhubo/data/<项目>.gen.json
# 什么时候改：场景表、生成要求或库字段变了（场景表在 lib.py）
import argparse, json, os, re, subprocess, sys, time
sys.path.insert(0, "/opt/ai-office/zhubo")
import lib as L
import gen as G0

WORK = "/opt/ai-office/zhubo/data"
HX = "/opt/ai-office/huanxin"


def status(project, **kw):
    p = os.path.join(WORK, "%s.gen.json" % project)
    st = G0.load(p, {}) or {}
    st.update(kw); st["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(st, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def material_of(project):
    for name in (project, project.split("-")[0]):
        p = os.path.join(WORK, "%s_material.md" % name)
        if os.path.isfile(p): return open(p, encoding="utf-8").read()
    return ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--scene", default="")
    o = ap.parse_args()
    scenes = [s for s in L.SCENES if not o.scene or s[0] == o.scene]
    if not scenes: sys.exit("没有这个场景")
    status(o.project, running=True, scene=o.scene or "全部", started=time.strftime("%H:%M"), error="")
    try:
        card = G0.card_brief(o.project)
        r = subprocess.run(["python3", "/opt/ai-office/ygc/caozuo.py", "goods", "--project", card["项目"]], capture_output=True, text=True, timeout=900, cwd="/opt/ai-office/ygc")
        goods = json.loads(r.stdout.strip().splitlines()[-1])
        if not goods.get("ok"): raise RuntimeError("在售商品没读到：%s" % goods.get("error"))
        old = L.load(o.project) or {}
        kb = G0.load(WORK + "/%s_kb.json" % o.project.split("-")[0], []) or []
        material = material_of(o.project)
        edited = [{"场景": sc["name"], "标题": it["title"], "正文": it["text"]} for sc, it in L.all_items(old) if it.get("edited")]
        want = "\n".join("- %s（key=%s）：%s；写 %s" % (n, k, w, c) for k, n, w, c in scenes)
        schema = ('只输出一个 JSON 对象，不要任何其他文字：\n{"summary":"一句话：这个项目这阵子直播主打什么、为什么",'
                  '"scenes":[{"key":"场景 key","items":[{"title":"≤10 字，写这条讲什么（如：雪道怎么选、五次卡怎么算），不写风格","text":"主播当场说的话","src":["出处：商品:<ID> / 档案:<条目> / 资料:景区资料 / 规则:<文档名>"]}]}],'
                  '"compliance":[{"rule":"Q1.1 价格表述","ok":true,"note":""}],"missing":["缺的资料，写清要什么、谁能给"],'
                  '"doc_review":[{"module":"景区资料里的段落","kept":"用了什么","changes":[{"orig":"原句","why":"为什么改","new":"改成"}]}],"verify":["景区资料里要园方核实的事实"]}\n'
                  '只写下面这些场景：\n' + want)
        prompt = ("你是大千文旅 AI 办公室的直播运营员，为「%s」官方直播间写话术库。今天是 %s。\n"
                  "话术库是主播在直播间随时点开就念的一条条话：每条独立成段、30–150 字、口语、短句、有画面和情绪、能直接念；称呼观众用「家人们 / 朋友们」。\n"
                  "事实只能来自：在售商品（价格、包含、须知以它为准）、景区资料（项目方填写，园区、项目、周边以它为准）、项目档案。台词里不出现「资料」「原稿」「项目方」这类字眼，出处只写进 src。\n"
                  "合规必守：不用极限词、不贬低同行、不说原价和最低价、没开秒杀工具不说秒杀、不做商品里没有的承诺（随时退、随时约、库存不多、错过再等一年）、不诱导互动（扣 1 领福利这类）。价格可以用商品里的数做真实算术。\n"
                  "答疑每条一个真实会被问到的问题，标题写问题，正文以「有家人问……」开头直接回答。讲品每件商品一条，写清卖点、画面、价格、包含、必须讲清的须知和收口。\n"
                  "%s\n\n<技能定义>\n%s\n</技能定义>\n\n<在售商品 来客实时读取于 %s>\n%s\n</在售商品>\n\n<项目档案>\n%s\n</项目档案>\n\n%s"
                  "<平台规则摘录 知识库>\n%s\n</平台规则摘录>\n\n%s") % (
            card["项目"], time.strftime("%Y-%m-%d"),
            ("<主播手改过的话（保留不动，新写的别和它重复）>\n%s\n</主播手改过的话>" % json.dumps(edited, ensure_ascii=False)) if edited else "",
            G0.skill_text(), goods.get("read_at"), json.dumps(goods.get("goods"), ensure_ascii=False, indent=0),
            json.dumps(card, ensure_ascii=False, indent=0),
            ("<景区资料 项目方填写>\n%s\n</景区资料>\n\n" % material) if material else "",
            "\n".join("《%s》%s" % (k.get("title"), k.get("text")) for k in kb[:14]), schema)
        sys.path.insert(0, HX)
        for line in open(HX + "/.env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k, v)
        from app import engine
        engine.SYSTEM_GUARD = "【运行环境】无人值守批处理：不要读写文件、不要执行命令；只依据下面给出的材料写，材料里没有的不编。"
        t0 = time.time()
        raw = engine.run(prompt, lambda m: print(time.strftime("%H:%M:%S"), m, flush=True), out={}, use_mcp=False)
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        lib = L.load(o.project) or {"scenes": L.blank_scenes(), "hotkeys": []}
        have = {s["key"] for s in lib["scenes"]}
        for s in L.blank_scenes():
            if s["key"] not in have: lib["scenes"].append(s)
        order = {k: i for i, k in enumerate(L.KEYS)}
        lib["scenes"].sort(key=lambda s: order.get(s["key"], 99))
        for sc in data.get("scenes", []):
            if sc.get("key") in {s[0] for s in scenes}: L.merge_scene(lib, sc["key"], sc.get("items") or [])
        gmap = {str(g.get("product_id")): g for g in goods.get("goods", [])}
        lib["goods"] = {pid: {k: g.get(k) for k in ("name", "price_yuan", "use_window", "sold_window", "crowd", "refund", "limit", "stock", "state")} for pid, g in gmap.items()}
        if not o.scene:
            for k in ("summary", "compliance", "missing", "doc_review", "verify"):
                if data.get(k) is not None: lib[k] = data[k]
            lib["kb"] = [{"title": k.get("title"), "doc_id": k.get("doc_id")} for k in kb]
        lib["meta"] = dict(lib.get("meta") or {}, project_id=o.project, project=card["项目"], client=card.get("客户"),
                           goods_read_at=goods.get("read_at"), generated_at=time.strftime("%Y-%m-%d %H:%M"))
        L.save(o.project, lib)
        status(o.project, running=False, finished=time.strftime("%H:%M"), seconds=int(time.time() - t0))
        print("ok", o.project, o.scene or "全部", "%ds" % (time.time() - t0))
    except Exception as e:
        status(o.project, running=False, error=str(e)[:200])
        raise


if __name__ == "__main__":
    main()
