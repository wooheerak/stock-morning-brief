import os
import time
import tempfile
import requests
import json
from dotenv import load_dotenv

load_dotenv()

KAKAO_API_BASE = "https://kapi.kakao.com"
TOKEN_CACHE = os.path.join(tempfile.gettempdir(), "kakao_new_tokens.env")


def refresh_access_token() -> dict:
    """리프레시 토큰으로 새 액세스 토큰 발급. 매 실행 시 호출해야 함 (access_token 6시간 만료)."""
    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    refresh_token = os.getenv("KAKAO_REFRESH_TOKEN")

    if not rest_api_key or not refresh_token:
        print("[카카오] REST API 키 또는 리프레시 토큰 미설정")
        return {}

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

        new_access = token_data.get("access_token", "")
        new_refresh = token_data.get("refresh_token", "")  # 30일 이내 만료 시에만 반환
        refresh_expires_in = token_data.get("refresh_token_expires_in", 0)  # 초 단위

        # 리프레시 토큰 만료 임박 경고
        if refresh_expires_in:
            days_left = int(refresh_expires_in) // 86400
            if days_left < 7:
                print(f"🚨 [카카오] 리프레시 토큰 만료까지 {days_left}일 — GH_PAT 없으면 수동 갱신 필요!")
            elif days_left < 20:
                print(f"⚠️  [카카오] 리프레시 토큰 {days_left}일 남음 (자동 갱신 예정)")
            else:
                print(f"  [카카오] 리프레시 토큰 잔여: {days_left}일")

        # GitHub Actions workflow가 읽어서 Secrets 업데이트하는 캐시 파일
        with open(TOKEN_CACHE, "w") as f:
            f.write(f"KAKAO_ACCESS_TOKEN={new_access}\n")
            if new_refresh:
                f.write(f"KAKAO_REFRESH_TOKEN={new_refresh}\n")
            if refresh_expires_in:
                f.write(f"KAKAO_REFRESH_EXPIRES_IN={refresh_expires_in}\n")

        msg = "[카카오] 액세스 토큰 갱신 완료"
        if new_refresh:
            msg += " (리프레시 토큰도 갱신됨)"
        print(msg)
        return {"access_token": new_access, "refresh_token": new_refresh or refresh_token}
    except Exception as e:
        print(f"[카카오] 토큰 갱신 실패: {e}")
        return {}


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

    messages = _split_message(message, max_length=900)

    # 서비스 URL: 환경변수 우선, 없으면 GitHub 레포로 폴백
    service_url = os.getenv(
        "SERVICE_URL", "https://github.com/wooheerak/stock-morning-brief"
    )

    success = True
    for i, chunk in enumerate(messages):
        template = {
            "object_type": "text",
            "text": chunk,
            "link": {"web_url": service_url, "mobile_web_url": service_url},
        }
        if len(messages) > 1:
            template["text"] = f"[{i+1}/{len(messages)}]\n{chunk}"

        data = {"template_object": json.dumps(template, ensure_ascii=False)}
        sent = False
        for attempt in range(2):
            try:
                resp = requests.post(url, headers=headers, data=data, timeout=10)
                if resp.status_code == 200:
                    print(f"[카카오] 발송 성공 ({i+1}/{len(messages)})")
                    sent = True
                    break
                else:
                    print(f"[카카오] 발송 실패 ({i+1}번째, 시도{attempt+1}): {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"[카카오] 발송 오류 ({i+1}번째, 시도{attempt+1}): {e}")
            if attempt == 0:
                time.sleep(2)
        if not sent:
            success = False

        if i < len(messages) - 1:
            time.sleep(1)

    return success


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
