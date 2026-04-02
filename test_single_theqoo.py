"""더쿠에서 1건만 가져와서 인스타 업로드하는 테스트 스크립트"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from importlib import import_module
bot = import_module("4chan_gemini_bot")

# 더쿠만 강제 선택하도록 get_trending_post를 오버라이드
def get_trending_post_theqoo_only():
    posted_set = set(bot.load_posted_history())
    site_domain = "theqoo.net"
    config = bot.SITE_CONFIGS[site_domain]
    
    bot.logger.info(f"[테스트] 더쿠에서만 게시물을 수집합니다...")
    
    import random
    posts = bot._collect_posts_from_site(site_domain, posted_set)
    if not posts:
        bot.logger.warning("더쿠에서 새로운 게시물을 찾지 못했습니다.")
        return None, None, []
    
    target_post = random.choice(posts)
    bot.logger.info(f"[테스트] 타겟: '{target_post['title']}'")
    
    # 댓글 수집
    import time, random
    comments = []
    try:
        time.sleep(random.uniform(1.0, 2.0))
        from bs4 import BeautifulSoup
        p_res = bot.http_session.get(target_post['link'], headers=config['headers'], timeout=15)
        p_res.raise_for_status()
        p_soup = BeautifulSoup(p_res.text, 'html.parser')
        for sel in config['comment_selectors']:
            cmt_elements = p_soup.select(sel)
            for cmt in cmt_elements:
                text = cmt.get_text(strip=True)
                if len(text) > bot.MIN_COMMENT_LENGTH:
                    comments.append(text)
                if len(comments) >= bot.MAX_COMMENTS_COLLECT:
                    break
            if len(comments) >= bot.MIN_COMMENTS_THRESHOLD:
                break
    except Exception as e:
        bot.logger.warning(f"댓글 수집 에러: {e}")
    
    return target_post['title'], target_post['link'], comments

if __name__ == "__main__":
    bot.logger.info("=" * 50)
    bot.logger.info("[테스트] 더쿠 단건 업로드 시작")
    bot.logger.info("=" * 50)
    
    # 기존 임시파일 정리
    for f in os.listdir(bot.SCRIPT_DIR):
        if f.startswith(("carousel_", "temp_")) and f.endswith((".jpg", ".png")):
            try:
                os.remove(os.path.join(bot.SCRIPT_DIR, f))
            except OSError:
                pass
    
    op_title, op_link, op_comments = get_trending_post_theqoo_only()
    if not op_title:
        bot.logger.error("게시물을 찾지 못했습니다. 종료합니다.")
        sys.exit(1)
    
    bot.logger.info(f"제목: {op_title}")
    bot.logger.info(f"링크: {op_link}")
    bot.logger.info(f"댓글 {len(op_comments)}개 수집됨")
    
    body_img, cmt_img = bot.capture_post_screenshots(op_link)
    if not body_img:
        bot.logger.error("캡처 실패. 종료합니다.")
        sys.exit(1)
    
    image_paths = bot.create_carousel_images_hybrid(op_title, body_img, cmt_img)
    if not image_paths:
        bot.logger.error("이미지 생성 실패. 종료합니다.")
        sys.exit(1)
    
    caption = bot.generate_instagram_caption(op_title, op_comments)
    bot.logger.info(f"캡션:\n{caption}")
    
    # 테스트이므로 대기 시간 단축 (10~30초)
    import random, time
    delay = random.randint(10, 30)
    bot.logger.info(f"[테스트] {delay}초 대기 후 업로드...")
    time.sleep(delay)
    
    success = bot.upload_album(bot.IG_USERNAME, bot.IG_PASSWORD, image_paths, caption=caption)
    
    if success:
        history = bot.load_posted_history()
        history.append(op_link)
        bot.save_posted_history(history)
        bot.logger.info("[테스트] 더쿠 단건 업로드 성공!")
    else:
        bot.logger.error("[테스트] 업로드 실패!")
    
    # 임시 파일 정리
    temp_files = [p for p in image_paths if os.path.basename(p) != "follow_request.jpg"]
    temp_files += [body_img, cmt_img]
    for path in temp_files:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
