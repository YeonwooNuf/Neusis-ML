# db.py
import psycopg2

def get_conn():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="neusis",
        user="postgres",
        password="1234",
    )


ALLOWED_CATEGORIES = {"POLITICS", "ECONOMY", "SOCIETY", "CULTURE", "WORLD", "IT"}

def normalize_category(cat: str | None) -> str:
    if not cat:
        return "SOCIETY"

    cat = cat.strip()

    korean_map = {
        "정치": "POLITICS",
        "경제": "ECONOMY",
        "사회": "SOCIETY",
        "생활/문화": "CULTURE",
        "세계": "WORLD",
        "IT/과학": "IT",
    }
    cat = korean_map.get(cat, cat.upper())

    if cat not in ALLOWED_CATEGORIES:
        return "SOCIETY"

    return cat


# ✅ 백엔드 enum / DB check constraint와 동일하게 맞추기
DEFAULT_INGEST_STATUS = "PENDING"   # 분석 대기중


def insert_article(article: dict):

    conn = get_conn()
    cur = conn.cursor()

    try:
        data = article.copy()
        data["category"] = normalize_category(data.get("category"))
        data["author"] = data.get("author") or "UNKNOWN"
        data["content"] = data.get("content") or ""
        data["source"] = data.get("source") or ""
        data["image_url"] = data.get("image_url") or ""

        # 🔥 여기서 무조건 PENDING으로 세팅 (외부 값은 무시)
        data["ingest_status"] = DEFAULT_INGEST_STATUS

        sql = """
            INSERT INTO article
                (title, author, category, content,
                 published_at, source, url,
                 ingest_status, image_url, created_at, updated_at)
            VALUES
                (%(title)s, %(author)s, %(category)s, %(content)s,
                 %(published_at)s, %(source)s, %(url)s,
                 %(ingest_status)s, %(image_url)s, NOW(), NOW())
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                category = EXCLUDED.category,
                ingest_status = EXCLUDED.ingest_status,
                image_url = EXCLUDED.image_url,
                updated_at = NOW();
        """

        cur.execute(sql, data)
        conn.commit()

    finally:
        cur.close()
        conn.close()
