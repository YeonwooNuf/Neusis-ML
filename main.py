# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from crawler import crawl_section_page, crawl_article_detail
from db import insert_article  # ✅ db.py의 insert_article 사용

from analysis_openai import analyze_article_with_openai

class ArticleAnalysisRequest(BaseModel):
    title: str
    content: str


class ArticleAnalysisResponse(BaseModel):
    summary: str
    sentiment: str
    keywords: list[str]
    category: str

app = FastAPI()

@app.post("/analyze", response_model=ArticleAnalysisResponse)
async def analyze_article(req: ArticleAnalysisRequest):
    """
    프론트나 스프링부트에서 호출할 /analyze 엔드포인트
    """
    result = analyze_article_with_openai(req.title, req.content)

    # OpenAI 결과 dict → 응답 모델에 맞게 변환
    return ArticleAnalysisResponse(
        summary=result.get("summary", ""),
        sentiment=result.get("sentiment", "neutral"),
        keywords=result.get("keywords", []),
        category=result.get("category", "Society"),
    )

class ArticlePayload(BaseModel):
    # DB에 넣을 때 사용할 기사 정보 모델
    title: str
    author: Optional[str]
    category: str
    content: Optional[str]
    published_at: Optional[str]
    source: Optional[str]
    url: str
    origin_link: Optional[str]
    thumbnail: Optional[str]      # 목록에서 가져오는 썸네일
    image_url: Optional[str]      # 본문 이미지 (첫 장)
    ingest_status: str


@app.get("/crawl/send")
def crawl_and_save(
        section: str = "101",
        clicks: int = 3,
):
    """
    1) 네이버 섹션 페이지 크롤링
    2) 각 기사 상세 크롤링
    3) db.insert_article() 사용해서 PostgreSQL article 테이블에 저장
    """

    try:
        # 1) 섹션 페이지에서 기사 목록 크롤링
        section_articles = crawl_section_page(section, clicks)

        saved_count = 0
        payloads: List[ArticlePayload] = []

        for a in section_articles:
            link = a.get("link")
            if not link:
                continue

            # 2) 상세 페이지 크롤링 (crawler.py에서 dict 반환)
            detail = crawl_article_detail(link, section)

            payload = ArticlePayload(
                title=detail.get("title"),
                author=detail.get("author"),
                category=detail.get("category"),
                content=detail.get("content"),
                published_at=detail.get("published_at"),
                source=detail.get("source"),
                url=detail.get("url"),
                origin_link=detail.get("origin_link"),
                thumbnail=a.get("thumbnail"),              # 목록 썸네일
                image_url=detail.get("image_url"),
                ingest_status=detail.get("ingest_status", "INGESTED"),
            )
            payloads.append(payload)

            # 3) DB에 저장할 dict로 변환해서 insert_article 호출
            article_dict = {
                "title": payload.title,
                "author": payload.author or "UNKNOWN",
                "category": payload.category,                # POLITICS / ECONOMY / ...
                "content": payload.content or "",
                "published_at": payload.published_at,        # "YYYY-MM-DD HH:MM:SS" 형태
                "source": payload.source or "",
                "url": payload.url,
                "image_url": payload.image_url or "",
                "ingest_status": payload.ingest_status or "INGESTED",
            }

            insert_article(article_dict)
            saved_count += 1

        return {
            "crawled": len(payloads),
            "saved": saved_count,
        }

    except Exception as e:
        # 어디서 에러 났는지 확인하기 쉽게 500과 함께 메시지 반환
        raise HTTPException(status_code=500, detail=f"crawl_and_save 실패: {e}")
