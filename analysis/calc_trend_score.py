# import os
# import math
# from datetime import datetime, timezone, timedelta

# from dotenv import load_dotenv
# import psycopg2
# from psycopg2.extras import DictCursor

# print("🔹 [LOG] calc_trend_score.py import 시작")

# # 1) .env 로드
# load_dotenv()
# print("🔹 [LOG] .env 로드 완료")

# DB_HOST = os.getenv("DB_HOST")
# DB_PORT = os.getenv("DB_PORT")
# DB_NAME = os.getenv("DB_NAME")
# DB_USER = os.getenv("DB_USER")
# DB_PASSWORD = os.getenv("DB_PASSWORD")

# print(
#     f"[ENV CHECK]\nHOST={DB_HOST}\nPORT={DB_PORT}\nDB={DB_NAME}\nUSER={DB_USER}\n"
# )

# # 2) DB 연결
# try:
#     conn = psycopg2.connect(
#         host=DB_HOST,
#         port=DB_PORT,
#         dbname=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD,
#     )
#     print("[LOG] DB 연결 성공")
# except Exception as e:
#     print("[ERROR] DB 연결 실패:", e)
#     raise


# # 트렌드 계산 파라미터
# RECENT_KEYWORD_DAYS = 3   # 최근 N일 안 기사 기준으로 키워드 빈도 계산
# HALF_LIFE_DAYS = 7        # 7일 지나면 recency_score가 0.5가 되도록
# LAMBDA = math.log(2) / HALF_LIFE_DAYS  # 지수감쇠 계수


# def fetch_analyzed_articles():
#     """
#     ANALYZED 상태의 기사 + analysis_result + published_at + result_id 가져오기
#     """
#     print("[LOG] fetch_analyzed_articles() 호출")
#     with conn.cursor(cursor_factory=DictCursor) as cur:
#         cur.execute(
#             """
#             SELECT
#                 a.article_id,
#                 a.published_at,
#                 ar.result_id
#             FROM article a
#             JOIN analysis_result ar
#               ON ar.article_id = a.article_id
#             WHERE a.ingest_status = 'ANALYZED'
#               AND a.published_at IS NOT NULL;
#             """
#         )
#         rows = cur.fetchall()
#         print(f"[LOG] ANALYZED 기사 개수: {len(rows)}")
#         return rows


# def fetch_keywords_for_results():
#     """
#     모든 result_id에 대해 연결된 키워드 목록 조회
#     """
#     print("[LOG] fetch_keywords_for_results() 호출")
#     with conn.cursor(cursor_factory=DictCursor) as cur:
#         cur.execute(
#             """
#             SELECT result_id, keyword
#             FROM analysis_keywords;
#             """
#         )
#         rows = cur.fetchall()

#     result_keywords = {}
#     for row in rows:
#         rid = row["result_id"]
#         kw = (row["keyword"] or "").strip()
#         if not kw:
#             continue
#         result_keywords.setdefault(rid, set()).add(kw)

#     print(f"🔹 [LOG] 키워드가 있는 result_id 수: {len(result_keywords)}")
#     return result_keywords


# def compute_recency_score(published_at, now):
#     """
#     발행일 기준 recency_score 계산 (0~1)
#     """
#     # published_at이 timezone 없는 naive일 수도 있으니 처리
#     if published_at.tzinfo is None:
#         published_at = published_at.replace(tzinfo=timezone.utc)

#     diff_days = (now - published_at).total_seconds() / 86400.0
#     if diff_days < 0:
#         diff_days = 0  # 미래 기사 방어

#     score = math.exp(-LAMBDA * diff_days)  # 0 ~ 1
#     return max(0.0, min(1.0, score))


# def main():
#     print("[LOG] calc_trend_score main() 시작")

#     # 1) 기준 시간 (현재)
#     now = datetime.now(timezone.utc)
#     print(f"🔹 [LOG] now = {now.isoformat()}")

#     # 2) 분석 완료 기사 + 키워드 조회
#     articles = fetch_analyzed_articles()
#     if not articles:
#         print("[LOG] ANALYZED 상태의 기사가 없습니다. 종료.")
#         return

#     result_keywords = fetch_keywords_for_results()

#     # 3) 최근 N일 안의 기사들만 뽑아서 키워드 빈도 계산
#     recent_cutoff = now - timedelta(days=RECENT_KEYWORD_DAYS)
#     print(
#         f"[LOG] 최근 키워드 계산 기준: {RECENT_KEYWORD_DAYS}일 (cutoff={recent_cutoff.isoformat()})"
#     )

#     # article_id -> (result_id, published_at)
#     article_map = {}
#     for row in articles:
#         article_map[row["article_id"]] = {
#             "result_id": row["result_id"],
#             "published_at": row["published_at"],
#         }

#     # keyword -> 최근 N일 내 등장 article 수
#     keyword_freq = {}

#     for row in articles:
#         published_at = row["published_at"]
#         if published_at.tzinfo is None:
#             published_at = published_at.replace(tzinfo=timezone.utc)

#         if published_at < recent_cutoff:
#             continue

#         rid = row["result_id"]
#         kws = result_keywords.get(rid, set())
#         for kw in kws:
#             keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

#     if not keyword_freq:
#         print("[LOG] 최근 N일 내 키워드가 없습니다. topical_score는 0으로 처리.")
#         max_freq = 1
#     else:
#         max_freq = max(keyword_freq.values())

#     print(f"🔹 [LOG] 최근 N일 내 서로 출현한 키워드 종류 수: {len(keyword_freq)}, 최대 빈도: {max_freq}")

#     # 4) 각 기사별 trend_score 계산 및 UPDATE
#     updated_count = 0

#     with conn.cursor() as cur:
#         for row in articles:
#             article_id = row["article_id"]
#             result_id = row["result_id"]
#             published_at = row["published_at"]

#             recency = compute_recency_score(published_at, now)

#             kws = result_keywords.get(result_id, set())
#             if kws and keyword_freq:
#                 # 각 키워드에 대해 (빈도 / max_freq) 계산 → 평균
#                 scores = []
#                 for kw in kws:
#                     freq = keyword_freq.get(kw, 0)
#                     if freq <= 0:
#                         continue
#                     scores.append(freq / max_freq)

#                 if scores:
#                     topical = sum(scores) / len(scores)
#                 else:
#                     topical = 0.0
#             else:
#                 topical = 0.0

#             # 최종 trend_score (0~1)
#             trend_score = 0.7 * recency + 0.3 * topical
#             trend_score = round(trend_score, 2)  # 소수 6자리 정도로 제한

#             print(
#                 f"🔹 [LOG] article_id={article_id}, result_id={result_id}, "
#                 f"recency={recency:.3f}, topical={topical:.3f}, trend_score={trend_score:.3f}"
#             )

#             cur.execute(
#                 """
#                 UPDATE analysis_result
#                 SET trend_score = %s
#                 WHERE result_id = %s;
#                 """,
#                 (trend_score, result_id),
#             )
#             updated_count += 1

#     conn.commit()
#     print(f"[LOG] trend_score 업데이트 완료, 대상 기사 수={updated_count}")
#     conn.close()
#     print("[LOG] calc_trend_score 종료, DB 연결 닫음")


# if __name__ == "__main__":
#     print("[LOG] __main__ 블록 진입 (calc_trend_score)")
#     main()
