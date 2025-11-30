# analysis_openai.py
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

# .env 로드
load_dotenv()

# OpenAI 클라이언트 생성
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def _extract_json(text: str) -> str:
    """
    GPT가 ```json ... ``` 코드블럭으로 감싸서 줄 때도 있고,
    앞뒤에 설명 문장을 붙여줄 때도 있으니까,
    실제 JSON 부분만 잘라내는 헬퍼 함수.
    """
    if not text:
        return ""

    text = text.strip()

    # 1) ```json ... ``` 형태 제거
    if text.startswith("```"):
        # 첫 줄의 ```json 또는 ``` 제거
        text = re.sub(r"^```[a-zA-Z0-9_]*\s*", "", text)
        # 마지막 ``` 제거
        text = re.sub(r"\s*```$", "", text).strip()

    # 2) 가장 처음 '{' 부터 마지막 '}' 까지만 남기기
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return text.strip()


def analyze_article_with_openai(title: str, content: str) -> dict:
    """
    article 테이블의 title + content 를 받아서
    - summary: 한 문단 요약 (한국어)
    - sentiment: positive | neutral | negative ...
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
      "summary": "한 문단 요약을 한국어로",
      "sentiment": "POSITIVE | NEUTRAL | NEGATIVE | HOPEFUL | FEARFUL | ANGRY | SAD 중 하나(대문자)",
      "keywords": ["키워드1", "키워드2", "키워드3"]
    }}

    설명 문장 없이 JSON만 출력해.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "너는 JSON만 출력하는 뉴스 분석기야. 반드시 순수 JSON만 반환해."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        # 가능하면 JSON 모드 사용 (지원되는 모델에서만)
        response_format={"type": "json_object"},
    )

    result_text = response.choices[0].message.content
    print("🔍 [DEBUG] raw response:", repr(result_text))

    # GPT 응답에서 JSON 부분만 추출
    clean_text = _extract_json(result_text)

    try:
        result_json = json.loads(clean_text)
    except json.JSONDecodeError:
        # 혹시 여전히 깨지면 최소한 원문을 같이 남겨두기
        print("❌ [ERROR] JSONDecodeError, raw:", result_text)
        result_json = {
            "summary": "",
            "sentiment": "neutral",
            "keywords": [],
            "raw": result_text,
        }

    return result_json
