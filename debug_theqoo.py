import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

url = "https://theqoo.net/hot/4144378487"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        import time
        time.sleep(3)
        
        # 본문 셀렉터 후보 확인
        selectors = [
            '.article_content', '.rd_body', '.board_read', '.document_content',
            '.read_body', '#article_1', '.xe_content', '.content_view',
            '.post_content', '.rhymix_content', '.article-body'
        ]
        for sel in selectors:
            el = page.locator(sel)
            count = el.count()
            if count > 0:
                text_preview = el.first.inner_text()[:80]
                print(f'[FOUND] {sel}: {count}개 -> {text_preview}')
            else:
                print(f'[    ] {sel}: 0개')
        
        # 댓글 셀렉터 후보 확인
        print('\n--- 댓글 셀렉터 ---')
        cmt_selectors = [
            'ul.comment_list', '.comment_item .comment_content',
            '.fdb_lst_ul', '.cmt_list', '.comment-list', '.reply-list',
            '.comment_area', '.best_comment'
        ]
        for sel in cmt_selectors:
            el = page.locator(sel)
            count = el.count()
            print(f'{"[FOUND]" if count > 0 else "[    ]"} {sel}: {count}개')
    finally:
        browser.close()
