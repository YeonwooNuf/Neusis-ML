from fastapi import FastAPI
from crawler import crawl_section_page, crawl_article_detail
from pydantic import BaseModel
from typing import List, Optional
import requests as py_requests  # 네이버 요청이랑 헷갈리지 않게 이름 다르게

app = FastAPI()  # ← 딱 한 번만!

# FastAPI → Spring 로 기사 보내는 쪽
SPRING_INGEST_URL = "http://localhost:8080/internal/articles/ingest"  # 스프링 주소


# -------------------------------
# /crawl : 크롤링 결과만 반환
# -------------------------------
@app.get("/crawl")
def crawl(section: str = "101", clicks: int = 5, with_detail: bool = True):

    # 1) 섹션 페이지 크롤링
    section_articles = crawl_section_page(section, clicks)

    results = []

    # 2) 상세 페이지 크롤링
    for a in section_articles:
        link = a["link"]
        if not link:
            continue

        detail = crawl_article_detail(link, section) if with_detail else {}

        results.append({
            **a,
            **detail
        })

    return {
        "count": len(results),
        "articles": results
    }


# -------------------------------
# /crawl/send : 크롤링 + Spring으로 전송
# -------------------------------
class ArticlePayload(BaseModel):
    title: str
    author: Optional[str]
    category: str
    content: Optional[str]
    published_at: Optional[str]
    source: Optional[str]
    url: str
    origin_link: Optional[str]
    ingest_status: str


@app.get("/crawl/send")
def crawl_and_send(
        section: str = "101",  # 기본: ECONOMY
        clicks: int = 3,
):
    """
    1) 네이버 섹션 페이지 크롤링
    2) 각 기사 상세 크롤링 → ArticlePayload 리스트로 변환
    3) Spring Boot 엔드포인트로 POST
    """

    # 1) 섹션 페이지에서 링크 목록 크롤링
    section_articles = crawl_section_page(section, clicks)

    articles: List[ArticlePayload] = []

    for a in section_articles:
        link = a["link"]
        if not link:
            continue

        # 2) 상세 페이지 크롤링 → Article 엔티티 형태 딕셔너리
        detail = crawl_article_detail(link, section)

        payload = ArticlePayload(
            title=detail["title"],
            author=detail["author"],
            category=detail["category"],
            content=detail["content"],
            published_at=detail["published_at"],
            source=detail["source"],
            url=detail["url"],
            origin_link=detail["origin_link"],
            ingest_status=detail["ingest_status"],
        )
        articles.append(payload)

    # 3) Spring Boot로 POST
    resp = py_requests.post(
        SPRING_INGEST_URL,
        json=[a.dict() for a in articles],
        timeout=30,
    )

    return {
        "sent_count": len(articles),
        "spring_status": resp.status_code,
        "spring_response": resp.json()
        if resp.headers.get("content-type", "").startswith("application/json")
        else resp.text,
    }
