import time
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


# -------------------------------
# Selenium Setup
# -------------------------------
def get_driver():
    chrome_driver_path = r"D:\chromedriver-win64\chromedriver.exe"  # 네 PC 경로

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


# -------------------------------
# "3시간 전", "25분 전" 파싱
# -------------------------------
def parse_relative_time(t):
    if not t:
        return None
    if "시간전" in t:
        h = int(t.replace("시간전", "").strip())
        return h * 60
    if "분전" in t:
        m = int(t.replace("분전", "").strip())
        return m
    return None


# -------------------------------
# section 코드 → category 문자열 매핑
# -------------------------------
def section_to_category(section: str) -> str:
    mapping = {
        "100": "POLITICS",
        "101": "ECONOMY",
        "102": "SOCIETY",
        "103": "CULTURE",
        "104": "WORLD",
        "105": "IT",
    }
    return mapping.get(section, "SOCIETY")  # 기본값 아무거나 하나 지정


# -------------------------------
# 섹션 페이지 크롤링 (목록만)
# -------------------------------
def crawl_section_page(section, clicks=10):
    driver = get_driver()
    url = f"https://news.naver.com/section/{section}"
    driver.get(url)

    # "더보기" 여러 번 클릭
    for _ in range(clicks):
        try:
            more_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".section_more_inner._CONTENT_LIST_LOAD_MORE_BUTTON")
                )
            )
            ActionChains(driver).move_to_element(more_button).click().perform()
            time.sleep(1.5)
        except Exception:
            break

    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")

    articles = []

    for item in soup.select(".sa_item_inner"):
        title_el = item.select_one(".sa_text_title._NLOG_IMPRESSION")
        time_el = item.select_one(".sa_text_datetime b")
        img_el = item.find("img")

        link = title_el.get("href") if title_el else None
        title = title_el.get_text(strip=True) if title_el else None
        img = img_el.get("src") if img_el else None
        time_text = time_el.get_text(strip=True) if time_el else None

        articles.append(
            {
                "title": title,
                "link": link,
                "thumbnail": img,
                "time": time_text,
            }
        )

    return articles


# -------------------------------
# 상세 페이지 크롤링 → Article 엔티티 형태로 반환
# -------------------------------
def crawl_article_detail(url: str, section: str):
    """
    네이버 기사 상세 페이지를 열어서
    Article 테이블에 바로 넣을 수 있는 형태로 변환.
    """
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 제목
    title_tag = soup.find("h2", class_="media_end_head_headline")
    title = title_tag.get_text(strip=True) if title_tag else None

    # 본문(네이버 기사 본문 id="dic_area")
    body_tag = soup.find("article", id="dic_area")
    content = body_tag.get_text("\n", strip=True) if body_tag else None

    # 날짜 (data-date-time 속성)
    date_tag = soup.find(
        "span", class_="media_end_head_info_datestamp_time _ARTICLE_DATE_TIME"
    )
    date_time = date_tag.get("data-date-time") if date_tag else None
    # 그대로 published_at 에 넣고, Spring 쪽에서 LocalDateTime 으로 파싱하면 됨

    # 원본 링크
    origin_link_tag = soup.find("a", class_="media_end_head_origin_link")
    origin_link = origin_link_tag.get("href") if origin_link_tag else None

    # 기자명 (author)
    # 네이버 구조가 조금씩 바뀔 수 있어서 몇 가지 셀렉터 시도
    author = None
    author_selectors = [
        ".media_end_head_journalist_name",
        ".byline",
        ".reporter",
    ]
    for sel in author_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            author = tag.get_text(strip=True)
            break
    if not author:
        author = "UNKNOWN"

    # 언론사명 (source)
    source = None
    media_logo = soup.select_one(".media_end_head_top_logo img")
    if media_logo and media_logo.get("alt"):
        source = media_logo.get("alt").strip()
    else:
        # fallback: meta 태그에서 시도
        og_site = soup.find("meta", property="og:article:author")
        if og_site and og_site.get("content"):
            source = og_site.get("content").strip()
    if not source:
        source = "UNKNOWN"

    # 카테고리
    category = section_to_category(section)

    # ingest_status
    ingest_status = "INGESTED" if content else "FAILED"

    # Article 엔티티에 바로 매핑 가능한 구조로 반환
    article_entity = {
        "title": title,             # 기사 제목
        "author": author,           # 네이버 모바일 뉴스 상세 페이지
        "category": category,
        "content": content,
        "published_at": date_time,  # 그대로 문자열로 두고, 백엔드에서 파싱
        "source": source,
        "url": url,                 # 네이버 뉴스 URL
        "origin_link": origin_link, # 필요 없으면 나중에 무시
        "ingest_status": ingest_status,
    }

    return article_entity
