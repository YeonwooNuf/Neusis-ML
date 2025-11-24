import os
import platform
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
# ChromeDriver Path Resolver
# -------------------------------
def get_chromedriver_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))   # crawler.py 기준
    driver_dir = os.path.join(base_dir, "chromedriver")

    system = platform.system()

    # macOS (Darwin)
    if system == "Darwin":
        path = os.path.join(driver_dir, "mac", "chromedriver")
        return path

    # Windows
    if system == "Windows":
        path = os.path.join(driver_dir, "win", "chromedriver.exe")
        return path

    raise RuntimeError(f"Unsupported OS: {system}")


# -------------------------------
# Selenium Setup
# -------------------------------
def get_driver():
    chrome_driver_path = get_chromedriver_path()

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(chrome_driver_path)
    return webdriver.Chrome(service=service, options=options)


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
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 제목
    title_tag = soup.find("h2", class_="media_end_head_headline")
    title = title_tag.get_text(strip=True) if title_tag else None

    # 본문
    body_tag = soup.find("article", id="dic_area")
    content = body_tag.get_text("\n", strip=True) if body_tag else None

    # 발행일시
    date_tag = soup.find(
        "span",
        class_="media_end_head_info_datestamp_time _ARTICLE_DATE_TIME"
    )
    published_at = date_tag.get("data-date-time") if date_tag else None
    # 예: "2025-11-18 18:19:45"

    # 원본 링크(지금은 DB에 안 넣지만 참고용)
    origin_link_tag = soup.find("a", class_="media_end_head_origin_link")
    origin_link = origin_link_tag.get("href") if origin_link_tag else None

    # 기자명
    author = None
    for sel in [".media_end_head_journalist_name", ".byline", ".reporter"]:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            author = tag.get_text(strip=True)
            break

    # 언론사명
    source = None
    media_logo = soup.select_one(".media_end_head_top_logo img")
    if media_logo and media_logo.get("alt"):
        source = media_logo.get("alt").strip()

    # 본문 이미지 중 첫 번째
    image_url = None

    # 1) 기사 본문 영역 안의 img 태그 우선 탐색
    img_tag = soup.select_one("article#dic_area img")
    if img_tag and img_tag.get("src"):
        image_url = img_tag.get("src")

    # 2) 그래도 없으면 og:image 메타 태그 fallback
    if not image_url:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image_url = og_img.get("content")

    print("IMG:", image_url)

    # 섹션 → 카테고리 ENUM 값
    category = section_to_category(section)

    return {
        "title": title,
        "author": author,
        "category": category,
        "content": content,
        "published_at": published_at,
        "source": source,
        "url": url,
        "origin_link": origin_link,
        "image_url": image_url,
        "ingest_status": "INGESTED" if content else "FAILED",
    }