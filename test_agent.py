#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PaperAgent 自测：用假 LLM 验证 决策→动作→落盘 闭环（无需 API Key）。"""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_agent as pa
from paper_agent import State

class MockLLM:
    """模拟 LLM：带【可用动作】的调用返回决策 JSON，其余返回正文。"""
    def __init__(self):
        self.calls = []

    def chat(self, msgs, json_mode=False, **kw):
        full = str([m.get("content", "") for m in msgs if isinstance(m, dict)])
        full = full.replace("\\n", "\n")  # str(list) 把换行转义了，先还原
        self.calls.append(full[:40])
        if "【可用动作】" not in full:
            return "这是模拟正文：论点清晰，论证充分，符合学术规范。【待用户核实】的引用已标注。"
        m = re.search(r"【已有文件】([^\n]*)", full)
        files = m.group(1).strip() if m else ""
        if "outline.md" not in files and "proposal.md" in files:
            return '{"action":"outline","args":{},"message":"大纲走起"}'
        if "outline.md" in files and not any(f.strip().startswith("sec-") for f in files.split(",")):
            return '{"action":"draft","args":{"section":"引言"},"message":"起草引言"}'
        if any(f.strip().startswith("sec-") for f in files.split(",")) and "critique.md" not in files:
            return '{"action":"critique","args":{},"message":"审一遍"}'
        if "critique.md" in files and "references.md" not in files:
            return '{"action":"references","args":{},"message":"汇总引用"}'
        if "references.md" in files and "check_report.md" not in files:
            return '{"action":"check","args":{},"message":"体检"}'
        if "check_report.md" in files and "final.md" not in files:
            return '{"action":"finalize","args":{},"message":"出终稿"}'
        if "proposal.md" not in files:
            return '{"action":"propose","args":{},"message":"先定位选题"}'
        return '{"action":"talk","args":{},"message":"全部完成"}'

    def plain(self, text):
        return text

def test_flow():
    st = State("test-paper")
    st.d["topic"] = "测试论文：注意力机制在图像分类中的应用"
    st.save()
    llm = MockLLM()
    steps = []
    steps.append(pa.build_agent(llm, st, "从选题开始，一路自动推进到终稿"))
    # 连续推进直到 final.md 出现
    for _ in range(12):
        if "final.md" in st.d["files"]:
            break
        steps.append(pa.build_agent(llm, st, "继续：下一步该做什么就做什么"))
    files = sorted(st.d["files"])
    ok = ("proposal.md" in files and "outline.md" in files
          and any(f.startswith("sec-") for f in files) and "final.md" in files)
    print("动作序列:", [s[:26] for s in steps])
    print("产出文件:", files)
    print("终稿开头:", st.read("final.md")[:60].replace("\n", " "))
    print("结果:", "PASS ✔" if ok else "FAIL ✘")
    return ok

if __name__ == "__main__":
    sys.exit(0 if test_flow() else 1)