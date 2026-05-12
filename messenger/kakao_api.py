import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

KAKAO_API_BASE = "https://kapi.kakao.com"


def send_to_me(message: str) -> bool:
    """나에게 보내기 API — 텍스트 메시지 발송"""
    access_token = os.getenv("KAKAO_ACCESS_TOKEN")
    if not access_token:
        print("[카카오] KAKAO_ACCESS_TOKEN 미설정")
        return False

    url = f"{KAKAO_API_BASE}/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # 2000자 초과 시 분할 발송
    messages = _split_message(message, max_length=1900)

    success = True
    for i, chunk in enumerate(messages):
        template = {
            "object_type": "text",
            "text": chunk,
            "link": {"web_url": "http://localhost:5000", "mobile_web_url": "http://localhost:5000"},
        }
        if len(messages) > 1:
            template["text"] = f"[{i+1}/{len(messages)}]\n{chunk}"

        data = {"template_object": json.dumps(template, ensure_ascii=False)}
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=10)
            if resp.status_code != 200:
                print(f"[카카오] 발송 실패 ({i+1}번째): {resp.status_code} {resp.text}")
                success = False
            else:
                print(f"[카카오] 발송 성공 ({i+1}/{len(messages)})")
        except Exception as e:
            print(f"[카카오] 발송 오류: {e}")
            success = False

    return success


def refresh_access_token() -> str | None:
    """액세스 토큰 갱신"""
    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    refresh_token = os.getenv("KAKAO_REFRESH_TOKEN")

    if not rest_api_key or not refresh_token:
        print("[카카오] REST API 키 또는 리프레시 토큰 미설정")
        return None

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
    }

    try:
        resp = requests.post(url, data=data, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()
        new_token = token_data.get("access_token")
        print(f"[카카오] 액세스 토큰 갱신 완료")
        return new_token
    except Exception as e:
        print(f"[카카오] 토큰 갱신 실패: {e}")
        return None


def _split_message(message: str, max_length: int = 1900) -> list:
    if len(message) <= max_length:
        return [message]

    chunks = []
    while message:
        chunk = message[:max_length]
        last_newline = chunk.rfind("\n")
        if last_newline > max_length // 2:
            chunk = message[:last_newline]
        chunks.append(chunk)
        message = message[len(chunk):].lstrip("\n")
    return chunks
