import os

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

from analysis_openai import analyze_article_with_openai

print("🔹 [LOG] run_openai_for_articles.py import 시작")

# .env 로드
load_dotenv()
print("🔹 [LOG] .env 로드 완료")

# 1) DB 연결 생성
try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "neusis"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "1234"),
    )
    print("🔹 [LOG] DB 연결 성공")
except Exception as e:
    print("❌ [ERROR] DB 연결 실패:", e)
    raise


def fetch_target_articles(limit: int = 5):
    """
    아직 analysis_result에 없는 article 몇 개 가져오기.
    """
    print(f"🔹 [LOG] fetch_target_articles() 호출, limit={limit}")
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
        print(f"🔹 [LOG] 가져온 기사 개수: {len(rows)}")
        return rows


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

    # ✅ DB가 허용하는 5가지 값
    allowed = {"POSITIVE", "NEUTRAL", "NEGATIVE", "HOPEFUL", "ANXIOUS"}

    # ✅ GPT가 줄 수 있는 감정을 DB 스킴에 맞게 변환
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
                trend_score,
                article_id
            )
            VALUES (
                NOW(),
                NOW(),
                %s,
                %s,
                %s,
                %s
            )
            RETURNING result_id;
            """,
            (sentiment, summary, 0.0, article_id),
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
    print(f"✅ [LOG] article_id={article_id} 전체 저장 커밋 완료\n")


def main():
    print("🚀 [LOG] main() 시작")

    # 1) 분석할 기사 가져오기
    articles = fetch_target_articles(limit=5)

    if not articles:
        print("ℹ️ [LOG] 분석할 대상 기사가 없습니다.")
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
        print("🔹 [LOG] OpenAI 분석 호출")
        analysis = analyze_article_with_openai(title, content)

        print("요약 :", analysis.get("summary"))
        print("감정 :", analysis.get("sentiment"))
        print("키워드 :", analysis.get("keywords"))
        print()

        # 3) DB 저장
        save_analysis_to_db(article_id, analysis)

    conn.close()
    print("🎉 [LOG] 모든 작업 완료, DB 연결 종료")


if __name__ == "__main__":
    print("🔹 [LOG] __main__ 블록 진입")
    main()
