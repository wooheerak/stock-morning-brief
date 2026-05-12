"""
카카오 액세스 토큰 최초 발급 도우미
실행: python kakao_auth.py
"""
import os
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv, set_key

load_dotenv()

REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
REDIRECT_URI = "http://localhost:5000/callback"
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>인증 완료! 창을 닫으세요.</h2>".encode("utf-8"))
            print(f"[OK] 인증 코드 수신: {auth_code[:20]}...")
        else:
            self.send_response(400)
            self.end_headers()
            print(f"[오류] 잘못된 콜백: {self.path}")

    def log_message(self, *args):
        pass


def get_access_token(code: str) -> dict:
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
    }
    print(f"[요청] 토큰 발급 요청 중...")
    resp = requests.post(url, data=data, timeout=10)
    print(f"[응답] 상태 코드: {resp.status_code}")
    if resp.status_code != 200:
        print(f"[오류] 응답 내용: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def main():
    if not REST_API_KEY:
        print("[오류] .env 파일에 KAKAO_REST_API_KEY가 없습니다.")
        sys.exit(1)

    print(f"[설정] REST API 키: {REST_API_KEY[:10]}...")
    print(f"[설정] .env 파일 경로: {ENV_FILE}")

    auth_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=talk_message"
    )

    print(f"\n브라우저에서 카카오 로그인 페이지가 열립니다...")
    webbrowser.open(auth_url)

    print("콜백 대기 중... (로그인 완료 후 자동 진행)")
    server = HTTPServer(("localhost", 5000), CallbackHandler)
    server.handle_request()

    if not auth_code:
        print("[오류] 인증 코드를 받지 못했습니다.")
        sys.exit(1)

    try:
        tokens = get_access_token(auth_code)
    except Exception as e:
        print(f"[오류] 토큰 발급 실패: {e}")
        sys.exit(1)

    print(f"\n[토큰 응답] {list(tokens.keys())}")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if access_token:
        set_key(ENV_FILE, "KAKAO_ACCESS_TOKEN", access_token)
        print(f"[저장] 액세스 토큰 저장 완료")
    else:
        print(f"[오류] 액세스 토큰 없음. 전체 응답: {tokens}")

    if refresh_token:
        set_key(ENV_FILE, "KAKAO_REFRESH_TOKEN", refresh_token)
        print(f"[저장] 리프레시 토큰 저장 완료")

    print("\n완료! 이제 python main.py 를 실행할 수 있습니다.")


if __name__ == "__main__":
    main()
