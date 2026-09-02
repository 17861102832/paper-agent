@echo off
chcp 65001 >nul
title PaperAgent - 论文 Agent
setlocal
cd /d "%~dp0"
echo ============================================
echo   PaperAgent · 论文 Agent
echo   全自动：new | 交互：chat | 续写：resume
echo ============================================
echo.
if "%1"=="" (
  echo 用法示例:
  echo   PaperAgent new "你的论文题目" --key sk-xxx
  echo   PaperAgent chat --base-url http://localhost:11434/v1 --model qwen2.5 --key ollama
  echo   PaperAgent chat --model gpt-4o-mini --key sk-xxx
  echo.
  echo 任何 OpenAI 兼容接口都能接：DeepSeek / OpenAI / Kimi / 通义 / Ollama 本地。
  echo.
  set /p CMD="输入指令: "
  python paper_agent.py %CMD% 2>nul || python paper_agent.py
) else (
  python paper_agent.py %*
)
echo.
pause