# PaperAgent

一个真的会写论文的 Agent：给它题目，它自己完成 选题定位 → 大纲 → 逐节起草 → 自我审稿 → 参考文献 → 体检 → 终稿。

## 用法

```bat
python paper_agent.py new "你的论文题目" --key sk-xxx    :: 全自动模式
python paper_agent.py chat --key sk-xxx                 :: 交互模式，自然语言指挥它
python paper_agent.py resume 题目简称                    :: 中断后续写，进度不丢
```

- API Key 三选一：`--key` 参数 / 环境变量 `DEEPSEEK_API_KEY` / 首次运行输入
- 所有产物在 `papers/<项目名>/`：proposal / outline / 章节草稿 / 审稿意见 / 参考文献 / 终稿
- 随时 Ctrl+C，下次 `resume` 从断点继续
- 无 Key 也能跑测试：`python test_agent.py` 验证 Agent 决策闭环

## 它自己会干的活

1. 选题定位：研究问题、对象、意义、思路
2. 列大纲：章节 + 每节要点
3. 逐节起草：写完一节再下一节，不是一次性糊完
4. 自我审稿：以审稿人身份挑毛病
5. 参考文献：汇总引用，拿不准的标【待用户核实】，不编造
6. 机械体检：章节完整性、占位符残留
7. 拼终稿：摘要 + 正文 + 参考文献

## 自测

```bat
python test_agent.py   :: 输出 PASS 即闭环正常（无需 API Key）
```

MIT。