"""Fix the corrupted section of 4chan_gemini_bot.py (lines 62-128)"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
target = os.path.join(SCRIPT_DIR, "4chan_gemini_bot.py")

with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the corrupted region and replace it
# Line 62 starts with "TITLE_MAX_TEXT_WIDTH" (0-indexed: 61)
# We need to find where "def load_posted_history():" starts

start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if 'UPLOAD_DELAY_RANGE' in line and start_idx is None:
        start_idx = i + 1  # line after UPLOAD_DELAY_RANGE
    if 'def load_posted_history():' in line:
        end_idx = i
        break

print(f"Replacing lines {start_idx+1} to {end_idx} (0-indexed: {start_idx} to {end_idx-1})")
print(f"Current content at boundaries:")
print(f"  Line {start_idx+1}: {lines[start_idx].rstrip()}")
print(f"  Line {end_idx+1}: {lines[end_idx].rstrip()}")

replacement = '''CAROUSEL_TARGET_SIZE = (1080, 1080)
MAX_CAROUSEL_IMAGES = 10

# \ud3f0\ud2b8 \uacbd\ub85c (\ubd07 \ud3f4\ub354 \ub0b4 \ubc88\ub4e4\ub9c1\ub41c \ud3f0\ud2b8 \uc6b0\uc120 \uc0ac\uc6a9)
FONT_BOLD = os.path.join(SCRIPT_DIR, "malgunbd.ttf")
FONT_REGULAR = os.path.join(SCRIPT_DIR, "malgun.ttf")
POSTED_HISTORY_FILE = os.path.join(SCRIPT_DIR, "posted_history.json")

# Gemini API \ucd08\uae30\ud654 (\ubaa8\ub4c8 \ub85c\ub4dc \uc2dc 1\ud68c\ub9cc \uc124\uc815)
if genai and GEMINI_API_KEY and "YOUR_" not in GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Gemini API \ucd08\uae30\ud654 \uc644\ub8cc")

# \ub124\ud2b8\uc6cc\ud06c \uc138\uc158 (\uc790\ub3d9 \uc7ac\uc2dc\ub3c4 \ud3ec\ud568)
http_session = requests.Session()
_retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
http_session.mount("https://", HTTPAdapter(max_retries=_retry_strategy))
http_session.mount("http://", HTTPAdapter(max_retries=_retry_strategy))

def get_font(size, bold=True):
    """\ud3f0\ud2b8\ub97c \uc548\uc804\ud558\uac8c \ub85c\ub4dc\ud569\ub2c8\ub2e4."""
    paths = [FONT_BOLD, FONT_REGULAR, "malgunbd.ttf", "malgun.ttf"] if bold else [FONT_REGULAR, FONT_BOLD, "malgun.ttf", "malgunbd.ttf"]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    logger.warning("\uc2dc\uc2a4\ud15c\uc5d0\uc11c \ud55c\uae00 \ud3f0\ud2b8\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uae30\ubcf8 \ud3f0\ud2b8\ub97c \uc0ac\uc6a9\ud569\ub2c8\ub2e4.")
    return ImageFont.load_default()

def strip_emoji_and_special(text):
    """\uc774\ubaa8\uc9c0/\ud2b9\uc218\ubb38\uc790\ub97c \uc81c\uac70\ud569\ub2c8\ub2e4. \ud55c\uae00\uc740 \ubcf4\uc874\ud569\ub2c8\ub2e4."""
    cleaned = []
    for ch in text:
        cp = ord(ch)
        # \uae30\ubcf8 ASCII + \ud55c\uae00 \uc790\ubaa8 + \ud55c\uae00 \uc644\uc131\ud615 + \uae30\ubcf8 \uad6c\ub450\uc810 \ud5c8\uc6a9
        if cp < 0x2600 or (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF) or (0x3131 <= cp <= 0x318E):
            cleaned.append(ch)
    result = ''.join(cleaned)
    return ' '.join(result.split())

'''

lines[start_idx:end_idx] = [replacement]

with open(target, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fix applied successfully!")
