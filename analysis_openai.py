# analysis_openai.py
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

# .env 로드
load_dotenv()

# OpenAI 클라이언트 생성
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def analyze_article_with_openai(title: str, content: str) -> dict:
    """
    article 테이블의 title + content 를 받아서
    - summary: 한 줄 요약 (한국어)
    - sentiment: positive | neutral | negative
    - keywords: 키워드 리스트
    를 반환한다.
    """

    prompt = f"""
    너는 한국어 뉴스 기사를 분석하는 도우미야.

    아래 뉴스 기사를 분석해서 JSON 형식으로만 출력해.

    제목: {title}

    본문: {content}

    출력 형식(키 이름은 꼭 그대로 써):
    {{
      "summary": "한 줄 요약을 한국어로",
      "sentiment": "POSITIVE | NEUTRAL | NEGATIVE | HOPEFUL | FEARFUL | ANGRY | SAD 중 하나(대문자)",
      "keywords": ["키워드1", "키워드2", "키워드3"]
    }}

    설명 문장 없이 JSON만 출력해.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "너는 JSON만 출력하는 뉴스 분석기야."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    result_text = response.choices[0].message.content

    # GPT가 준 문자열을 JSON으로 파싱
    try:
        result_json = json.loads(result_text)
    except json.JSONDecodeError:
        # 혹시 JSON이 깨지면 최소한 기본값으로 반환
        result_json = {
            "summary": "",
            "sentiment": "neutral",
            "keywords": [],
            "raw": result_text,
        }

    return result_json
