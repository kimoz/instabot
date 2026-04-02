import os
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import textwrap
import json
import schedule
import logging
import re
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# ==========================================
# 로깅 설정
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'bot.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ==========================================
# 환경변수 로드 (.env 파일에서 읽기)
# ==========================================
load_dotenv()
IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ==========================================
# 상수 정의
# ==========================================
MAX_HISTORY_SIZE = 1000          # 히스토리 최대 보관 수
MIN_TITLE_LENGTH = 5             # 최소 제목 길이
MIN_COMMENT_LENGTH = 5           # 최소 댓글 길이
MAX_COMMENTS_COLLECT = 5         # 댓글 수집 최대 개수
MIN_COMMENTS_THRESHOLD = 3       # 댓글 수집 종료 임계값
MAX_HASHTAGS = 5                 # 해시태그 최대 개수
TITLE_MAX_TEXT_WIDTH = 970        # 썸네일 텍스트 최대 너비
TITLE_MAX_TEXT_HEIGHT = 500       # 썸네일 텍스트 최대 높이
UPLOAD_DELAY_RANGE = (60, 300)   # 업로드 전 대기 범위 (초)
CAROUSEL_TARGET_SIZE = (1080, 1080)
MAX_CAROUSEL_IMAGES = 10

# 광고/홍보성 및 특정 주제 제외 키워드 (이 단어들이 포함된 제목은 수집하지 않음)
AD_KEYWORDS = [
    "광고", "홍보", "추천인", "수익", "부업", "공구", "판매", "구매", "협찬", 
    "체험단", "서포터즈", "가입", "이벤트", "적립", "쿠폰", "할인코드", "코드입력",
    "방탄", "BTS", "방탄소년단", "남초", "여초", "여초반응", "남초반응"
]

# 폰트 경로 (봇 폴더 내 번들링된 폰트 우선 사용)
FONT_BOLD = os.path.join(SCRIPT_DIR, "malgunbd.ttf")
FONT_REGULAR = os.path.join(SCRIPT_DIR, "malgun.ttf")
POSTED_HISTORY_FILE = os.path.join(SCRIPT_DIR, "posted_history.json")

# Gemini API 초기화 (모듈 로드 시 1회만 설정)
if genai and GEMINI_API_KEY and "YOUR_" not in GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Gemini API 초기화 완료")

# 네트워크 세션 (자동 재시도 포함)
http_session = requests.Session()
_retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
http_session.mount("https://", HTTPAdapter(max_retries=_retry_strategy))
http_session.mount("http://", HTTPAdapter(max_retries=_retry_strategy))

def get_font(size, bold=True):
    """폰트를 안전하게 로드합니다."""
    paths = [FONT_BOLD, FONT_REGULAR, "malgunbd.ttf", "malgun.ttf"] if bold else [FONT_REGULAR, FONT_BOLD, "malgun.ttf", "malgunbd.ttf"]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    logger.warning("시스템에서 한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
    return ImageFont.load_default()

def strip_emoji_and_special(text):
    """이모지/특수문자를 제거합니다. 한글은 보존합니다."""
    cleaned = []
    for ch in text:
        cp = ord(ch)
        # 기본 ASCII + 한글 자모 + 한글 완성형 + 기본 구두점 허용
        if cp < 0x2600 or (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF) or (0x3131 <= cp <= 0x318E):
            cleaned.append(ch)
    result = ''.join(cleaned)
    return ' '.join(result.split())

def load_posted_history():
    """이미 올린 게시물 URL 목록을 불러옵니다."""
    if os.path.exists(POSTED_HISTORY_FILE):
        try:
            with open(POSTED_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def save_posted_history(history):
    """올린 게시물 URL 목록을 저장합니다. 최근 N개만 유지합니다."""
    history = history[-MAX_HISTORY_SIZE:]
    with open(POSTED_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ==========================================
# 1. Gemini 캡션 생성
# ==========================================
# 인용 가능한 추천 해시태그 풀 (AI 실패 시 랜덤으로 번갈아가며 사용)
TAG_POOL = [
    "#네이트판 #실시간인기 #커뮤니티레전드 #오늘의톡 #서이추 #유머스타그램 #꿀잼 #대박사건 #실화냐 #이슈 #정보공유 #소통해요 #일상기록 #맞팔환영 #인기게시물",
    "#웃긴짤 #유머글 #네이트판레전드 #주간랭킹 #이슈포착 #썰 #공감글 #힐링 #심심할때 #시간순삭 #직장인스타그램 #대학생공감 #재밌는글 #팔로우미 #좋아요반사",
    "#커뮤니티툰 #네이트판후기 #썰모음 #웃음코드 #일상유머 #트렌드 #실시간이슈 #핫이슈 #공감짤 #보물창고 #웃음지뢰 #핵잼 #꿀정보 #인스타데일리 #소식나눔"
]

def add_watermark(img, text="@1dayhumor"):
    """이미지 우측 하단에 반투명 워터마크를 추가합니다."""
    draw = ImageDraw.Draw(img)
    # 이미지 크기에 맞춰 폰트 사이즈 조절 (이미지 가로의 약 3.5%)
    font_size = int(img.width * 0.035)
    font = get_font(font_size, bold=True)
    
    # 텍스트 위치 계산 (우측 하단 여백)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = 20
    pos = (img.width - tw - margin, img.height - th - margin)
    
    # 가독성을 위한 검은색 외곽선 (살짝)
    offset = 2
    for dx in [-offset, 0, offset]:
        for dy in [-offset, 0, offset]:
            draw.text((pos[0]+dx, pos[1]+dy), text, fill="black", font=font)
    
    # 메인 흰색 텍스트
    draw.text(pos, text, fill="white", font=font)
    return img

def generate_instagram_caption(title, comments):
    logger.info(f"알고리즘 최적화 캡션 생성 중: '{title}'")
    
    # [1. CLEAN TOP] 불필요한 점(.) 나열 대신 깔끔한 제목
    caption_top = f"📢 {title}\n\n"
    
    # [2. DYNAMIC FALLBACK]
    fallback_tags = "#1dayhumor #오늘의톡 #꿀잼 #이슈"
    
    if not genai or not GEMINI_API_KEY or "YOUR_" in GEMINI_API_KEY:
        return caption_top + "오늘도 즐거운 하루 되세요! 😊\n\n" + fallback_tags
        
    try:
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        comments_str = "\n".join([f"- {c}" for c in comments[:5]])
        
        prompt = f"""
        게시물 제목: "{title}"
        베스트 댓글:
        {comments_str}

        위의 내용을 분석해서 다음 형식으로 인스타그램 캡션을 작성해줘.
        1. 게시물 주제와 관련된 재미있는 소감 한 줄 (예: 공감된다, 대박이다 등)
        2. 사용자 참여를 유도하는 질문 (예: 여러분은 어떤가요?, 이런 경험 있으신가요? 등)
        3. 게시물 핵심 키워드로 된 해시태그 3~5개만 (오직 '#'으로 시작하는 태그만 나열)

        - 다른 말(인사말, 요약)은 일체 하지 말 것.
        - 오직 캡션 본문과 태그 3~5개만 출력할 것.
        - 점(.)을 길게 나열하는 구식 방식은 금지.
        """

        response = model.generate_content(prompt)
        ai_caption = response.text.strip()
        
        # 해시태그 개수 강제 제한 (혹시 많이 나왔을 경우 대비)
        lines = ai_caption.split('\n')
        final_lines = []
        tags_found = []
        for line in lines:
            if "#" in line:
                for word in line.split():
                    if word.startswith("#") and len(tags_found) < 5:
                        tags_found.append(word)
            else:
                final_lines.append(line)
        
        tag_str = " ".join(tags_found) if tags_found else fallback_tags
        final_caption = f"{caption_top}" + "\n".join(final_lines).strip() + f"\n\n.\n{tag_str}"
        
        logger.info(f"최종 캡션 준비 완료 (태그 {len(tags_found)}개 사용)")
        return final_caption
    except Exception as e:
        logger.error(f"Gemini 캡션 생성 에러: {e}")
        return caption_top + "오늘의 핫이슈! 함께 봐요 😊\n\n" + fallback_tags


# 사이트별 설정 (네이트판 & 더쿠)
SITE_CONFIGS = {
    "pann.nate.com": {
        "name": "네이트판",
        "sources": [
            {"name": "주간 랭킹", "url": "https://pann.nate.com/talk/ranking/w"},
            {"name": "결시친 채널", "url": "https://pann.nate.com/talk/c20025/channel?type=2"}
        ],
        "list_selector": "div.cntList ul li dl dt a, .cntList a[title], .cntList li h2 a, .best ul.post_list li h2 a, .tbl_list td.subject a",
        "content_selector": ".posting",
        "comment_selectors": ["div.cmt_best ul li dl dt.cmt_str", "div.list_cmt ul li dl dt.cmt_str", ".usertxt"],
        "visual_comment_selectors": ['.cmt_best', '.cmt_list', '.reply-list', '#replyArea'],
        "headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
    },
    "theqoo.net": {
        "name": "더쿠",
        "sources": [
            {"name": "핫 게시판", "url": "https://theqoo.net/hot"}
        ],
        "list_selector": "td.title a:not(.replyNum)",
        "content_selector": ".rd_body",
        "comment_selectors": [".fdb_lst_ul .xe_content"],
        "visual_comment_selectors": [".fdb_lst_ul"],
        "headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://theqoo.net/'
        }
    }
}

# ==========================================
# 2. 통합 인기글 수집 (네이트판 & 더쿠)
# ==========================================
def _collect_posts_from_site(site_domain, posted_set):
    """특정 사이트에서 유효한 게시물 목록을 수집합니다."""
    config = SITE_CONFIGS[site_domain]
    valid_posts = []
    seen_links = set()

    for source in config['sources']:
        logger.info(f"[{config['name']}] '{source['name']}' 스캔 중...")
        try:
            res = http_session.get(source['url'], headers=config['headers'], timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')

            items = soup.select(config['list_selector'])
            for item in items:
                href = item.get('href', '')
                if not href:
                    continue

                if not href.startswith('http'):
                    full_link = f"https://{site_domain}" + (href if href.startswith('/') else f"/{href}")
                else:
                    full_link = href

                if full_link in seen_links:
                    continue
                seen_links.add(full_link)

                if full_link in posted_set:
                    continue

                title = item.get_text(strip=True)
                if len(title) < MIN_TITLE_LENGTH:
                    continue

                # 광고성 키워드 필터링
                if any(kw in title for kw in AD_KEYWORDS):
                    logger.info(f"[{config['name']}] 광고성 글로 의심되어 제외합니다: '{title}'")
                    continue

                valid_posts.append({"title": title, "link": full_link, "source": source['name']})
        except Exception as e:
            logger.error(f"'{source['name']}' 스캔 중 에러: {e}")

    return valid_posts


def get_trending_post():
    """인기 게시물 1건을 선정하고 댓글을 수집합니다. 실패 시 (None, None, []) 반환."""
    posted_set = set(load_posted_history())  # O(1) 검색을 위한 set 변환

    # 사이트 순서를 랜덤 셔플 (자동 fallback 포함)
    site_domains = list(SITE_CONFIGS.keys())
    random.shuffle(site_domains)

    all_valid_posts = []
    selected_domain = None

    for site_domain in site_domains:
        config = SITE_CONFIGS[site_domain]
        logger.info(f"[{config['name']}]에서 게시물을 스캔합니다...")

        posts = _collect_posts_from_site(site_domain, posted_set)
        if posts:
            all_valid_posts = posts
            selected_domain = site_domain
            break
        else:
            logger.warning(f"[{config['name']}]에 새로 올릴 게시물이 없습니다. 다른 사이트로 전환합니다...")

    if not all_valid_posts or not selected_domain:
        logger.warning("모든 사이트에서 새로 올릴 게시물을 찾지 못했습니다.")
        return None, None, []

    config = SITE_CONFIGS[selected_domain]
    target_post = random.choice(all_valid_posts)
    logger.info(f"타겟 게시물 선정 ({target_post['source']}): '{target_post['title']}'")

    # 상세 페이지에서 댓글 텍스트 수집 (AI용)
    comments = []
    try:
        time.sleep(random.uniform(1.0, 2.0))
        p_res = http_session.get(target_post['link'], headers=config['headers'], timeout=15)
        p_res.raise_for_status()
        p_soup = BeautifulSoup(p_res.text, 'html.parser')

        for sel in config['comment_selectors']:
            cmt_elements = p_soup.select(sel)
            for cmt in cmt_elements:
                text = cmt.get_text(strip=True)
                if len(text) > MIN_COMMENT_LENGTH:
                    comments.append(text)
                if len(comments) >= MAX_COMMENTS_COLLECT:
                    break
            if len(comments) >= MIN_COMMENTS_THRESHOLD:
                break

    except Exception as e:
        logger.warning(f"댓글 텍스트 수집 중 에러(무시 가능): {e}")

    return target_post['title'], target_post['link'], comments


# ==========================================
# 3. Playwright 브라우저 캡처
# ==========================================
def capture_post_screenshots(url):
    # 도메인에 따른 설정 찾기
    domain = ""
    for d in SITE_CONFIGS.keys():
        if d in url:
            domain = d
            break
    
    if not domain:
        logger.error(f"알 수 없는 도메인 URL: {url}")
        return None, None
        
    config = SITE_CONFIGS[domain]
    logger.info(f"[{config['name']}] 로봇 브라우저 접속하여 화면 캡처 중...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={'width': 1200, 'height': 1080})
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                # 본문 요소 로드 대기
                try:
                    page.wait_for_selector(config['content_selector'], timeout=10000)
                except Exception:
                    logger.warning(f"본문 요소({config['content_selector']}) 대기 시간 초과, 현재 상태로 진행합니다.")
                
                # DOM 조작: 불필요한 UI 제거 + 익명화
                page.evaluate(f"""
                    // 공통: 헤더 및 네비게이션 숨기기
                    ['#header', '.pann-navi', 'header', 'nav', '.top_nav', '.bottom_nav'].forEach(s => {{
                        const el = document.querySelector(s);
                        if(el) el.style.display = 'none';
                    }});
                    
                    // 각 사이트별 광고/메뉴 추가 숨기기
                    ['.adsbygoogle', 'iframe', '.banner', '.footer'].forEach(s => {{
                        document.querySelectorAll(s).forEach(el => el.style.display = 'none');
                    }});
                    
                    // 더쿠 특화: 상단 메뉴바 등 제거
                    if (window.location.host.includes('theqoo.net')) {{
                        const menu = document.querySelector('.main_menu');
                        if(menu) menu.style.display = 'none';
                        const top_bar = document.querySelector('.top_bar');
                        if(top_bar) top_bar.style.display = 'none';
                    }}

                    // 작성자 익명화 처리
                    const nameElements = document.querySelectorAll('.nameui, .writer, .name, .nickname, .nick');
                    nameElements.forEach(el => {{
                        el.innerText = '익명';
                        el.style.filter = 'blur(4px)';
                    }});
                """)
                
                body_path = os.path.join(SCRIPT_DIR, 'temp_body.png')
                cmt_path = os.path.join(SCRIPT_DIR, 'temp_cmt.png')
                
                # 본문 캡처
                body_captured = False
                el = page.locator(config['content_selector'])
                if el.count() > 0:
                    el.first.screenshot(path=body_path)
                    body_captured = True
                
                if not body_captured:
                    logger.warning(f"[{config['name']}] 본문 요소를 찾을 수 없습니다.")
                    return None, None
                
                # 댓글 캡처 (리스트 중 존재하는 첫 번째 영역 캡처)
                found_cmt = False
                for sel in config['visual_comment_selectors']:
                    el = page.locator(sel)
                    if el.count() > 0:
                        # 더쿠: 비회원 댓글 제한 문구가 있으면 댓글 캡처 건너뛰기
                        cmt_text = el.first.inner_text()
                        if '비회원은 작성한 지' in cmt_text and '댓글은 읽을 수 없습니다' in cmt_text:
                            logger.info("[더쿠] 비회원 댓글 제한 문구 감지 — 댓글 캡처를 건너뜁니다.")
                            break
                        el.first.screenshot(path=cmt_path)
                        found_cmt = True
                        break
                
                logger.info("화면 캡처 완료!")
                return body_path, cmt_path
            finally:
                browser.close()
    except Exception as e:
        logger.error(f"Playwright 캡처 에러: {e}")
        return None, None


# ==========================================
# 4. 이미지 슬라이싱 (1080x1080)
# ==========================================
def slice_screenshot(img_path, output_prefix, start_idx=1, target_size=(1080, 1080)):
    if not img_path or not os.path.exists(img_path):
        return [], start_idx
    
    img = Image.open(img_path)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    w, h = img.size
    new_w = target_size[0]
    new_h = int(h * (new_w / w))
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    slice_h = target_size[1]
    num_slices = (new_h + slice_h - 1) // slice_h
    paths = []
    idx = start_idx
    
    for i in range(num_slices):
        top = i * slice_h
        bottom = min((i + 1) * slice_h, new_h)
        slice_img = img.crop((0, top, new_w, bottom))
        
        if slice_img.size[1] < slice_h:
            padded = Image.new('RGB', target_size, (255, 255, 255))
            padded.paste(slice_img, (0, 0))
            slice_img = padded
        
        out_path = os.path.join(SCRIPT_DIR, f"carousel_{idx}_{output_prefix}.jpg")
        # 워터마크 추가
        slice_img = add_watermark(slice_img)
        slice_img.save(out_path, "JPEG", quality=95)
        paths.append(out_path)
        idx += 1
    
    return paths, idx


# ==========================================
# 5. 주황색 썸네일 + 슬라이스 카드뉴스 생성
# ==========================================
def create_carousel_images_hybrid(op_title, body_img_path, cmt_img_path):
    logger.info("주황색 썸네일 및 캡처본 슬라이싱 진행 중...")
    width, height = CAROUSEL_TARGET_SIZE
    image_paths = []
    bg_color = (255, 127, 39)
    
    # 이모지 및 특수문자 제거 (폰트 깨짐 방지)
    clean_title = strip_emoji_and_special(op_title)
    if not clean_title:
        clean_title = op_title  # fallback
    
    # 동적 폰트 스케일링 (여유 있는 마진 적용)
    max_font_size = 80
    min_font_size = 36
    current_font_size = max_font_size
    max_text_w = 900   # 좌우 여백 90px씩
    max_text_h = 450   # 상하 여백 확보
    wrap_w = 10
    if len(clean_title) > 20: wrap_w = 9
    if len(clean_title) > 35: wrap_w = 8
    if len(clean_title) > 50: wrap_w = 7
    
    while current_font_size >= min_font_size:
        font_title = get_font(current_font_size, bold=True)
        wrapped_title = textwrap.fill(clean_title, width=wrap_w, break_long_words=True, replace_whitespace=False)
        
        draw_temp = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        bbox = draw_temp.textbbox((0, 0), wrapped_title, font=font_title, align="center", spacing=40)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        if text_w < max_text_w and text_h < max_text_h:
            break
        current_font_size -= 5

    # 썸네일 렌더링 (흰 글씨 + 검정 외곽선)
    thumb_image = Image.new('RGB', (width, height), color=bg_color)
    draw_t = ImageDraw.Draw(thumb_image)
    text_pos = (width / 2, height / 2)
    thickness = 5
    
    for adj in range(-thickness, thickness + 1):
        for adj2 in range(-thickness, thickness + 1):
            if adj == 0 and adj2 == 0:
                continue
            draw_t.text(
                (text_pos[0] + adj, text_pos[1] + adj2),
                wrapped_title, fill="black", font=font_title,
                anchor="mm", align="center", spacing=40
            )
    draw_t.text(text_pos, wrapped_title, fill="white", font=font_title, anchor="mm", align="center", spacing=40)
    
    # 썸네일 워터마크 추가
    thumb_image = add_watermark(thumb_image)
    
    thumb_path = os.path.join(SCRIPT_DIR, "carousel_0_thumb.jpg")
    thumb_image.save(thumb_path, "JPEG", quality=95)
    image_paths.append(thumb_path)
    
    # 본문 + 댓글 슬라이싱
    body_paths, next_idx = slice_screenshot(body_img_path, "body", start_idx=1)
    image_paths.extend(body_paths)
    cmt_paths, _ = slice_screenshot(cmt_img_path, "comment", start_idx=next_idx)
    image_paths.extend(cmt_paths)
    
    # 인스타그램 캐러셀 최대 10장 제한 (마지막 1장은 팔로우 요청용으로 예약)
    FOLLOW_IMG = os.path.join(SCRIPT_DIR, "follow_request.jpg")
    max_content = 9 if os.path.exists(FOLLOW_IMG) else 10
    
    if len(image_paths) > max_content:
        for p in image_paths[max_content:]:
            try: os.remove(p)
            except OSError: pass
        image_paths = image_paths[:max_content]
    
    # 마지막에 팔로우 요청 이미지 삽입
    if os.path.exists(FOLLOW_IMG):
        image_paths.append(FOLLOW_IMG)
        
    # [최종 검증] 이미지가 너무 적으면 오류로 간주 (썸네일 + 본문 최소 1장 + 팔로우 최소 1장 = 3장 이상 권장)
    if len(image_paths) < 2:
        logger.error(f"이미지 생성 실패: {len(image_paths)}장뿐입니다. 업로드를 취소합니다.")
        return []

    logger.info(f"총 {len(image_paths)}장의 리얼 캡처 스타일 카드뉴스 썸네일 대기조 완성!")
    return image_paths


# ==========================================
# 6. 인스타그램 업로드
# ==========================================
def upload_album(username, password, image_paths, caption=""):
    logger.info(f"[{username}] 인스타 세션 로딩 및 로그인 시도 중...")
    cl = Client()
    session_file = os.path.join(SCRIPT_DIR, "ig_session.json")
    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        try:
            cl.login(username, password)
        except ChallengeRequired:
            logger.warning("Instagram 보안 인증 요청됨. 이메일/SMS로 전송된 코드를 입력하세요.")
            cl.challenge_resolve(cl.last_json)
            code = input("인증 코드 입력: ").strip()
            cl.challenge_send_security_code(code)
            logger.info("인증 완료. 업로드를 계속합니다.")
        except LoginRequired:
            logger.warning("세션 만료. 세션 파일 삭제 후 재로그인합니다.")
            if os.path.exists(session_file):
                os.remove(session_file)
            cl2 = Client()
            cl2.login(username, password)
            cl2.dump_settings(session_file)
            result = cl2.album_upload(image_paths, caption=caption)
            logger.info(f"다중 카드뉴스 자동 업로드 완료! URL: https://www.instagram.com/p/{result.code}/")
            return True
        cl.dump_settings(session_file)

        result = cl.album_upload(image_paths, caption=caption)
        logger.info(f"다중 카드뉴스 자동 업로드 완료! URL: https://www.instagram.com/p/{result.code}/")
        return True
    except Exception as e:
        logger.error(f"인스타그램 업로드 에러: {type(e).__name__}: {e}")
        return False


# ==========================================
# 7. 메인 작업 함수
# ==========================================
def run_bot_job(test_mode=False):
    logger.info("=" * 50)
    logger.info("리얼 캡처 봇 출동!")
    logger.info("=" * 50)
    
    # [Proactive Cleanup] 기존에 남은 이미지 파일들 모두 제거 (민트색 등 방지)
    for f in os.listdir(SCRIPT_DIR):
        if f.startswith(("carousel_", "temp_")) and f.endswith((".jpg", ".png")):
            try:
                os.remove(os.path.join(SCRIPT_DIR, f))
            except OSError:
                pass
    
    op_title, op_link, op_comments = get_trending_post()
    if not op_title:
        logger.warning("게시물을 찾지 못했습니다. 다음 스케줄에 다시 시도합니다.")
        return
    
    body_img, cmt_img = capture_post_screenshots(op_link)
    if not body_img:
        logger.warning("캡처에 실패했습니다. 다음 스케줄에 다시 시도합니다.")
        return
    
    image_paths = create_carousel_images_hybrid(op_title, body_img, cmt_img)
    if not image_paths:
        logger.error("이미지 생성 단계에서 오류가 발생하여 업로드를 중단합니다.")
        return

    caption = generate_instagram_caption(op_title, op_comments)
    
    # [Human-like Delay] 업로드 직전 랜덤 대기 (테스트 모드에서는 생략)
    if not test_mode:
        delay = random.randint(*UPLOAD_DELAY_RANGE)
        logger.info(f"자동화 감지 방지를 위해 {delay}초 대기 후 업로드를 시작합니다...")
        time.sleep(delay)
    
    success = upload_album(IG_USERNAME, IG_PASSWORD, image_paths, caption=caption)
    
    # 업로드 성공 시 히스토리에 기록 (중복 방지)
    if success:
        history = load_posted_history()
        history.append(op_link)
        save_posted_history(history)
    
    # 임시 파일 정리 (팔로우 요청 원본 이미지는 절대 지우지 않음)
    temp_files = [p for p in image_paths if os.path.basename(p) != "follow_request.jpg"]
    temp_files += [body_img, cmt_img]
    
    for path in temp_files:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    
    if success:
        logger.info("100% 자가 분열 캡처 카드뉴스 업로드 퍼펙트 클리어!")
    else:
        logger.warning("업로드에 실패했습니다. 다음 스케줄에 재시도합니다.")


def setup_peak_schedules():
    """오전, 오후, 저녁 각 1회씩 랜덤한 시간에 포스팅을 예약합니다.
    
    Note: 자정 리셋 job은 __main__에서 별도로 등록합니다 (누적 방지).
    """
    # 포스팅 스케줄만 클리어 (자정 리셋 job은 'system' 태그로 보존)
    schedule.clear('posting')
    
    # [Target Slots] 오전, 오후, 저녁 고정 (밤 슬롯 제외)
    TARGET_SLOTS = [
        ("오전", 8, 10),
        ("오후", 12, 14),
        ("저녁", 19, 21)
    ]
    
    scheduled_times = []
    for name, start_h, end_h in TARGET_SLOTS:
        h = random.randint(start_h, end_h - 1)
        m = random.randint(0, 59)
        time_str = f"{h:02d}:{m:02d}"
        schedule.every().day.at(time_str).do(run_bot_job).tag('posting')
        scheduled_times.append(f"{name}({time_str})")
    
    logger.info(f"오늘의 3회 포스팅(오전/오후/저녁) 스케줄 예약 완료: {', '.join(scheduled_times)}")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("[네이트판/더쿠 -> 썸네일 & 본문/댓글 리얼 캡처 -> 인스타 업로드]")
    logger.info("=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        logger.info("[TEST] 테스트 모드: 스케줄러 없이 즉시 1회 실행합니다.")
        run_bot_job(test_mode=True)
        logger.info("[TEST] 테스트 완료.")
        sys.exit(0)

    # 1. 즉시 1회 실행 (운영 시작 확인용)
    logger.info("[START] 봇 가동을 시작하며 즉시 1회 업로드를 시도합니다.")
    run_bot_job()

    # 2. 피크 시간대 스케줄링 설정
    setup_peak_schedules()

    # 3. 매일 자정에 스케줄 갱신 (여기서 1회만 등록 — 무한 누적 방지)
    schedule.every().day.at("00:01").do(setup_peak_schedules).tag('system')

    logger.info("피크 시간대 스마트 스케줄러 가동 중.. zZZ")

    while True:
        schedule.run_pending()
        time.sleep(30)
