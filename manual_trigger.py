import sys
import os
import importlib.util

# 봇 스크립트 경로 지정 (숫자로 시작하는 파일명 임포트 처리)
bot_path = r"c:\Users\KEYMEDI\Desktop\InstaBot\4chan_gemini_bot.py"
spec = importlib.util.spec_from_file_location("bot_module", bot_path)
bot_module = importlib.util.module_from_spec(spec)
sys.modules["bot_module"] = bot_module
spec.loader.exec_module(bot_module)

if __name__ == "__main__":
    print("수동 업로드를 1회 즉시 실행합니다 (기존 업로드와 다른 게시물)...")
    bot_module.run_bot_job()
