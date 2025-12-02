import os

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

from analysis_openai import analyze_article_with_openai

print("🔹 [LOG] run_openai_for_articles.py import 시작")

# .env 로드
load_dotenv()
print("🔹 [LOG] .env 로드 완료")

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# 환경 변수 체크 (디버깅용, 민감 정보는 출력 X)
print(f"🔹 [ENV CHECK]\nHOST={DB_HOST}\nPORT={DB_PORT}\nDB={DB_NAME}\nUSER={DB_USER}\n")

# 1) DB 연결 생성
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    print("[LOG] DB 연결 성공")
except Exception as e:
    print("[ERROR] DB 연결 실패:", e)
    raise


def fetch_target_articles(limit: int = 5):
    """
    아직 analysis_result에 없는 article 몇 개 가져오기.
    """
    print(f"[LOG] fetch_target_articles() 호출, limit={limit}")
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            """
            SELECT a.article_id, a.title, a.content
            FROM article a
            LEFT JOIN analysis_result ar 
                   ON ar.article_id = a.article_id
            WHERE ar.article_id IS NULL
              AND a.content IS NOT NULL
            ORDER BY a.article_id DESC
            LIMIT %s;
            """,
            (limit,),
        )
        rows = cur.fetchall()
        print(f"[LOG] 가져온 기사 개수: {len(rows)}")
        return rows


def update_article_status(article_id: int, status: str):
    """
    article 테이블의 ingest_status 업데이트
    status: 'ANALYZED', 'FAILED' 등
    """
    print(f"[LOG] article_id={article_id} ingest_status -> {status}")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE article
            SET ingest_status = %s
            WHERE article_id = %s;
            """,
            (status, article_id),
        )
    conn.commit()


def save_analysis_to_db(article_id: int, analysis: dict):
    """
    OpenAI 분석 결과를 analysis_result, analysis_keywords에 저장.
    sentiment는 DB 제약 조건( POSITIVE / NEUTRAL / NEGATIVE / HOPEFUL / ANXIOUS )
    에 맞도록 매핑해서 넣는다.
    """
    print(f"🔹 [LOG] save_analysis_to_db() 호출, article_id={article_id}")

    summary = (analysis.get("summary") or "").strip()
    sentiment = (analysis.get("sentiment") or "NEUTRAL").strip().upper()
    keywords = analysis.get("keywords") or []

    # DB가 허용하는 5가지 값
    allowed = {"POSITIVE", "NEUTRAL", "NEGATIVE", "HOPEFUL", "ANXIOUS"}

    # GPT가 줄 수 있는 감정을 DB 스킴에 맞게 변환
    mapping = {
        "FEARFUL": "ANXIOUS",
        "FEAR": "ANXIOUS",
        "AFRAID": "ANXIOUS",
        "ANGRY": "NEGATIVE",
        "SAD": "NEGATIVE",
    }

    if sentiment in mapping:
        print(f"🔹 [LOG] sentiment 매핑: {sentiment} -> {mapping[sentiment]}")
        sentiment = mapping[sentiment]

    if sentiment not in allowed:
        print(f"🔹 [LOG] sentiment {sentiment} 허용값 아님 → NEUTRAL로 변경")
        sentiment = "NEUTRAL"

    with conn.cursor() as cur:
        # 1) analysis_result 추가
        cur.execute(
            """
            INSERT INTO analysis_result (
                created_at,
                processed_at,
                sentiment,
                summary,
                article_id
            )
            VALUES (NOW(), NOW(), %s, %s, %s)
            RETURNING result_id;
            """,
            (sentiment, summary, article_id),
        )
        result_id = cur.fetchone()[0]
        print(f"🔹 [LOG] analysis_result 저장 완료, result_id={result_id}")

        # 2) analysis_keywords 추가
        for kw in keywords:
            kw_str = str(kw).strip()
            if not kw_str:
                continue

            cur.execute(
                """
                INSERT INTO analysis_keywords (result_id, keyword)
                VALUES (%s, %s);
                """,
                (result_id, kw_str),
            )
        print(f"🔹 [LOG] analysis_keywords {len(keywords)}개 저장 완료")

    conn.commit()
    print(f"[LOG] article_id={article_id} 전체 저장 커밋 완료\n")


def main():
    print("[LOG] main() 시작")

    # 1) 분석할 기사 가져오기
    articles = fetch_target_articles(limit=5)

    if not articles:
        print("[LOG] 분석할 대상 기사가 없습니다.")
        return

    for row in articles:
        article_id = row["article_id"]
        title = row["title"]
        content = row["content"] or ""

        print("=" * 80)
        print(f"[article_id={article_id}] {title}")
        print("- 원문 일부:")
        print(content[:200].strip(), "...\n")

        # 2) OpenAI로 분석
        print("[LOG] OpenAI 분석 호출")
        analysis = analyze_article_with_openai(title, content)

        summary_raw = (analysis.get("summary") or "").strip()
        sentiment_raw = (analysis.get("sentiment") or "").strip()
        keywords_raw = analysis.get("keywords") or []

        print("요약 :", summary_raw)
        print("감정 :", sentiment_raw)
        print("키워드 :", keywords_raw)
        print()

        # ============================
        # 3) 성공 / 실패 판정 로직
        # ============================

        # 요약 존재 여부
        ok_summary = bool(summary_raw)

        # 키워드 정제 (빈 문자열 제거)
        if isinstance(keywords_raw, (list, tuple)):
            valid_keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
        else:
            valid_keywords = []
        ok_keywords = len(valid_keywords) > 0

        # 감정 레이블 존재 여부
        ok_sentiment = bool(sentiment_raw)

        if not (ok_summary and ok_keywords and ok_sentiment):
            print(
                f"[LOG] article_id={article_id} 분석 실패 "
                f"(summary_ok={ok_summary}, keywords_ok={ok_keywords}, sentiment_ok={ok_sentiment})"
            )
            # 실패 → ingest_status = FAILED, 분석결과는 저장 안 함
            update_article_status(article_id, "FAILED")
            continue

        # 성공 케이스: 정제된 값으로 analysis 덮어쓰기
        analysis["summary"] = summary_raw
        analysis["sentiment"] = sentiment_raw
        analysis["keywords"] = valid_keywords

        # 4) DB 저장
        save_analysis_to_db(article_id, analysis)

        # 5) article.ingest_status = ANALYZED
        update_article_status(article_id, "ANALYZED")

    conn.close()
    print("[LOG] 모든 작업 완료, DB 연결 종료")


if __name__ == "__main__":
    print("[LOG] __main__ 블록 진입")
    main()
