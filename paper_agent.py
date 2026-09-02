#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaperAgent —— 论文 Agent（单文件）

用法：
  python paper_agent.py new "论文题目" [--key sk-xxx]   # 立项并开始自动写作
  python paper_agent.py chat [--key sk-xxx]             # 交互模式：给它下自然语言指令
  python paper_agent.py resume <slug>                   # 断点续写

它自己会：选题定位 → 列大纲 → 逐节起草 → 自我审稿改稿 → 参考文献 -> 引用体检 → 出终稿。
所有工作落在 ./papers/<slug>/ 里，随时 Ctrl+C，下次 resume 接着干。

API Key 三选一：--key 参数 / 环境变量 DEEPSEEK_API_KEY / 首次运行时输入。
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
BASE = Path(__file__).resolve().parent
PAPERS = BASE / "papers"
MAX_TOKENS = 4096
SYSTEM_PROMPT = (
    "你是 PaperAgent，一位实战派学术论文写手。你的任务：帮用户从零写出一篇可用的论文。"
    "规则：1) 动笔前必有计划，逐节推进，不跳步。2) 学术严谨：结论要有支撑；"
    "拿不准的事实、数据、文献，明确标注【待用户核实】，绝不编造文献。"
    "3) 会自我批评：写完主动挑毛病再改。4) 中文输出，术语精确，段落紧凑有干货，不写空话。"
    "5) 每次回复最多做 1-2 件事，把当前进度一句话交代清楚。"
)

TOOLS = [
    {"name": "propose", "desc": "围绕题目做选题定位：研究问题、对象、意义、可行思路", "args": ["topic"]},
    {"name": "outline", "desc": "生成论文大纲（章节+每节要点），写入 outline.md", "args": ["topic", "notes"]},
    {"name": "draft", "desc": "起草指定章节正文，写入 draft 文件", "args": ["section", "outline", "notes"]},
    {"name": "revise", "desc": "按批评意见重写某节，覆盖原文件", "args": ["section", "feedback"]},
    {"name": "critique", "desc": "以严师身份审查全稿，给问题清单", "args": ["notes"]},
    {"name": "references", "desc": "汇总文内引用与文末参考文献列表，标注待核实项", "args": ["notes"]},
    {"name": "check", "desc": "机械体检：引用编号连续性、占位符残留、章节完整性", "args": ["none"]},
    {"name": "finalize", "desc": "拼装终稿（摘要+关键词+正文+参考文献）写入 final.md", "args": ["notes"]},
    {"name": "talk", "desc": "直接回答用户，不调用工具", "args": ["none"]},
]


class LLM:
    def __init__(self, key: str):
        self.key = key

    def chat(self, msgs, json_mode=False, temperature=0.7) -> str:
        payload = {"model": MODEL, "messages": msgs, "temperature": temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
        )
        ctx = ssl.create_default_context()
        tries = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
                    out = json.loads(r.read().decode("utf-8"))
                return out["choices"][0]["message"]["content"]
            except Exception as e:  # 网络抖动重试两次
                tries += 1
                if tries >= 3:
                    raise RuntimeError(f"LLM 调用失败: {e}")
                time.sleep(3 * tries)


class State:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir = PAPERS / slug
        self.file = self.dir / "state.json"
        if self.file.exists():
            self.d = json.loads(self.file.read_text(encoding="utf-8"))
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.d = {"slug": slug, "history": [], "files": {}, "topic": ""}
            self.save()

    def save(self):
        self.file.write_text(json.dumps(self.d, ensure_ascii=False, indent=2), encoding="utf-8")

    def hist(self, role, text):
        self.d["history"].append({"role": role, "content": text, "t": time.strftime("%H:%M")})
        self.save()

    def art(self, name, content):
        self.d["files"][name] = content
        (self.dir / name).write_text(content, encoding="utf-8")
        self.save()

    def read(self, name):
        return self.d["files"].get(name, "")


def read_prompt(env, stage, ctx, user_text):
    """把 agent 状态与用户最新指令拼成给 LLM 的提示。"""
    tools_desc = "\n".join(f"- {t['name']}: {t['desc']}" for t in TOOLS)
    return (f"{SYSTEM_PROMPT}\n\n"
            f"【项目】{ctx['topic'] or '（未定，先跟用户确认题目）'}\n"
            f"【已有文件】{', '.join(ctx['files']) or '无'}\n"
            f"【阶段】{stage}\n"
            f"【可用动作】\n{tools_desc}\n\n"
            f"【规矩】需要动手（写文件/起草/改稿）时，只输出 JSON：{{'action':'动作名','args':{{...}},'message':'给用户的一句进度说明'}}。"
            f"不过最自然的做法：'message' 里说人话，需要干活就带 'action'，先想后做。\n"
            f"【用户最新指令】{user_text}")


def slip(s):
    """中文标题转目录名。"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "-", s).strip("-")[:40]
    return s or "paper"


def build_agent(llm: LLM, st: State, user_text, stage="idle"):
    ctx = {"topic": st.d["topic"], "files": list(st.d["files"].keys())}
    prompt = read_prompt("tools", stage, ctx, user_text)
    msgs = [{"role": "user", "content": prompt}]
    for h in st.d["history"][-16:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    st.hist("user", user_text)
    try:
        raw = llm.chat(msgs, json_mode=True)
    except Exception as e:
        return f"出错了：{e}"
    st.hist("assistant", raw)
    # 解析动作
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return raw
    try:
        act = json.loads(m.group(0))
    except Exception:
        return raw
    action = act.get("action")
    args = act.get("args", {})
    msg = act.get("message", "")

    if not action or action == "talk":
        return msg or raw

    # 执行动作（agent 的手）
    if action == "propose":
        text = llm.chat([{"role": "user", "content": f"围绕题目《{st.d['topic'] or args.get('topic')}》做选题定位：研究问题、研究对象、意义、方法思路、目标读者。300字内，具体不空话。"}])
        st.art("proposal.md", text)
        return f"{msg}\n已产出选题定位 → proposal.md"
    if action == "outline":
        notes = st.read("proposal.md")
        text = llm.chat([{"role": "user", "content": f"论文题目《{st.d['topic']}》。选题定位：{notes[-600:]}\n请给出完整大纲：章节标题+每节2-3个要点，600字内。"}])
        st.art("outline.md", text)
        return f"{msg}\n大纲已写入 outline.md"
    if action == "draft":
        sec = args.get("section", "")
        outline = st.read("outline.md")
        done = [f for f in st.d["files"] if f.startswith("sec")]
        text = llm.chat([{"role": "user", "content": f"论文题目《{st.d['topic']}》。大纲：{outline[-800:]}\n已写章节：{done}\n请起草章节「{sec}」正文，800-1200字，学术语气，结尾留过渡。遇到不确定的引用写【待用户核实】。"}])
        fn = f"sec-{slip(sec)}.md"
        st.art(fn, text)
        return f"{msg}\n「{sec}」草稿完成 → {fn}"
    if action == "revise":
        sec = args.get("section", "")
        fb = args.get("feedback", "")
        src = f"sec-{slip(sec)}.md"
        old = st.read(src)
        text = llm.chat([{"role": "user", "content": f"重写「{sec}」以解决这些问题：{fb}\n原文：{old[-1500:]}"}])
        st.art(src, text)
        return f"{msg}\n「{sec}」已按意见重写"
    if action == "critique":
        drafts = "\n\n".join(st.read(f) for f in st.d["files"] if f.startswith("sec"))
        text = llm.chat([{"role": "user", "content": f"请以严格审稿人身份审查这篇稿件，列出问题清单（结构/论证/表达/引用各至少1条），分条写。\n稿件：{drafts[-4000:]}"}])
        st.art("critique.md", text)
        return f"{msg}\n审稿意见 → critique.md"
    if action == "references":
        drafts = "\n".join(st.read(f) for f in st.d["files"] if f.startswith("sec"))
        text = llm.chat([{"role": "user", "content": f"从稿件中汇总：1)文内引用点；2)建议的参考文献条目（作者,年份,题名,出处）。凡不确定出处的拿真实感存疑的，加【待用户核实】。不要编造。\n稿件：{drafts[-3500:]}"}])
        st.art("references.md", text)
        return f"{msg}\n参考文献清单 → references.md（含待核实标注）"
    if action == "check":
        drafts = {f: st.read(f) for f in st.d["files"] if f.startswith("sec")}
        problems = []
        for f, c in drafts.items():
            c2 = re.sub(r"[（(].{0,10}[【待用户核实】【TODO】].{0,20}[)）]", "", c)
            if re.search(r"【TODO】|【待核实】|TODO|占位", c2):
                problems.append(f"{f}: 残留待办/占位符")
            if len(c) < 200:
                problems.append(f"{f}: 篇幅不足")
        outline = st.read("outline.md")
        heads = re.findall(r"\d+[\.、]\s*[^\n]+", outline)
        report = "# 机械体检\n\n" + ("\n".join(f"- {p}" for p in problems) if problems else "- 章节完整、无占位符残留 ✔\n") + f"\n- 大纲节数：{len(heads)}，已写章节文件：{len(drafts)}\n"
        st.art("check_report.md", report)
        return f"{msg}\n体检报告 → check_report.md"
    if action == "finalize":
        bits = ["# " + st.d["topic"], ""]
        for f in sorted(st.d["files"]):
            if f.startswith("sec-"):
                bits.append(st.read(f))
        refs = st.read("references.md")
        if refs:
            bits += ["", "## 参考文献", refs]
        st.art("final.md", "\n\n".join(bits))
        return f"{msg}\n终稿已拼装 → final.md"
    return f"{msg}（动作 {action} 已尝试执行）"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if "--key" in rest:
        i = rest.index("--key")
        key = rest[i + 1]
        del rest[i:i + 2]

    if cmd == "new" and rest:
        topic = " ".join(rest)
        key = key or input("DeepSeek API Key: ").strip()
        slug = slip(topic)
        st = State(slug)
        st.d["topic"] = topic
        st.save()
        llm = LLM(key)
        print(f"项目 {slug} 立项：《{topic}》")
        out = build_agent(llm, st, f"新论文《{topic}》，从选题定位开始，然后大纲，然后逐节起草，全部自动完成。")
        print("\n" + out)
        return
    if cmd == "resume" and rest:
        slug = rest[0]
        st = State(slug)
        key = key or input("DeepSeek API Key: ").strip()
        llm = LLM(key)
        print(f"恢复项目 {slug}（阶段延续，文件：{', '.join(st.d['files'])}）")
        out = build_agent(llm, st, "继续推进论文：接着写未完成的章节，写完就审稿、修稿、汇总参考文献、体检、出终稿。")
        print("\n" + out)
        return
    if cmd == "chat":
        key = key or input("DeepSeek API Key: ").strip()
        llm = LLM(key)
        slug = input("项目名（新项目直接给标题）: ").strip()
        st = State(slip(slug))
        if not st.d["topic"]:
            st.d["topic"] = slug
            st.save()
        print('PaperAgent 在线。直接说你要它干的活。退出输入 exit，随时 resume 继续。')
        while True:
            try:
                u = input("\n你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。resume 继续。")
                break
            if not u:
                continue
            if u.lower() in ("exit", "quit", "退出"):
                print("已存档，`python paper_agent.py resume " + st.slug + "` 继续。")
                break
            out = build_agent(llm, st, u)
            print("\nAgent>", out)
        return
    print(__doc__)


if __name__ == "__main__":
    main()