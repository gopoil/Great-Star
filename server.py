#!/usr/bin/env python3
"""마리코 채팅 서버.

비서실장 마리코와 대화하는 아이메시지 스타일 채팅창을 띄운다.

    python3 server.py            # http://localhost:8765

응답을 만드는 백엔드는 세 가지이고, 쓸 수 있는 것을 자동으로 고른다.

    cli   `claude` CLI를 헤드리스로 실행한다. 마리코/ 폴더를 작업 디렉터리로 쓰기
          때문에 CLAUDE.md와 부서 문서를 그대로 읽고, 파일도 직접 만들 수 있다.
    api   ANTHROPIC_API_KEY가 있고 anthropic 패키지가 깔려 있으면 Claude API를
          직접 호출한다. 대화만 가능하고 파일 작업은 하지 않는다.
    demo  둘 다 없을 때. 정해진 문구로 답한다. 화면 확인용.

환경 변수
    MARIKO_PORT             기본 8765
    MARIKO_HOST             기본 127.0.0.1
    MARIKO_BACKEND          auto | cli | api | demo   (기본 auto)
    MARIKO_MODEL            기본 claude-opus-5
    MARIKO_PERMISSION_MODE  cli 백엔드 권한 모드 (기본 acceptEdits)
    MARIKO_TIMEOUT          한 번의 응답 제한 시간(초). 기본 300
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSISTANT_DIR = ROOT / os.environ.get("MARIKO_DIR", "마리코")
INDEX_FILE = ROOT / "index.html"

HOST = os.environ.get("MARIKO_HOST", "127.0.0.1")
PORT = int(os.environ.get("MARIKO_PORT", "8765"))
MODEL = os.environ.get("MARIKO_MODEL", "claude-opus-5")
PERMISSION_MODE = os.environ.get("MARIKO_PERMISSION_MODE", "acceptEdits")
TIMEOUT = float(os.environ.get("MARIKO_TIMEOUT", "300"))

MAX_BODY = 256 * 1024


# ---------------------------------------------------------------- 백엔드 선택

def _has_sdk() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


# claude를 설치하고도 터미널을 새로 열지 않아 PATH에 안 잡히는 경우가 흔하다.
# 그래서 PATH에 없으면 흔한 설치 위치까지 찾아본다.
CLAUDE_CANDIDATES = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
)


def find_claude() -> str | None:
    override = os.environ.get("MARIKO_CLAUDE_BIN")
    if override:
        path = os.path.expanduser(override)
        return path if os.access(path, os.X_OK) else None
    found = shutil.which("claude")
    if found:
        return found
    for candidate in CLAUDE_CANDIDATES:
        path = os.path.expanduser(candidate)
        if os.access(path, os.X_OK):
            return path
    return None


CLAUDE_BIN = find_claude()


def pick_backend() -> str:
    want = os.environ.get("MARIKO_BACKEND", "auto").strip().lower()
    if want in ("cli", "api", "demo"):
        return want
    if CLAUDE_BIN:
        return "cli"
    if _has_sdk():
        return "api"
    return "demo"


BACKEND = pick_backend()


def load_profile() -> dict:
    path = ASSISTANT_DIR / "profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[마리코] profile.json을 읽지 못했습니다: {exc}", file=sys.stderr)
        return {"name": "비서", "title": "", "avatar": "비", "greeting": "무엇을 도와드릴까요?"}


# ------------------------------------------------------------------ 세션 관리

class Session:
    def __init__(self, sid: str):
        self.id = sid
        self.cli_session_id: str | None = None   # claude CLI 쪽 세션 id
        self.history: list[dict] = []            # api 백엔드용 대화 기록
        self.proc: subprocess.Popen | None = None
        self.cancelled = False
        self.lock = threading.Lock()

    def cancel(self) -> None:
        with self.lock:
            self.cancelled = True
            proc = self.proc
        if proc and proc.poll() is None:
            proc.terminate()


SESSIONS: dict[str, Session] = {}
SESSIONS_LOCK = threading.Lock()


def get_session(sid: str | None) -> Session:
    sid = sid or uuid.uuid4().hex
    with SESSIONS_LOCK:
        session = SESSIONS.get(sid)
        if session is None:
            session = Session(sid)
            SESSIONS[sid] = session
    return session


# ------------------------------------------------------------- cli 백엔드

# 도구 이름을 채팅창에 보여줄 한 줄짜리 상태 문구로 바꾼다.
TOOL_LABELS = {
    "Read": "자료를 확인하는 중",
    "Glob": "자료를 찾는 중",
    "Grep": "자료를 찾는 중",
    "Write": "문서를 작성하는 중",
    "Edit": "문서를 고치는 중",
    "Bash": "작업을 실행하는 중",
    "WebSearch": "검색하는 중",
    "WebFetch": "자료를 읽는 중",
    "Task": "부서에 배정하는 중",
    "TodoWrite": "할 일을 정리하는 중",
}


def _drain(stream, sink: list) -> None:
    try:
        for line in stream:
            sink.append(line)
    except (ValueError, OSError):
        pass


def stream_cli(session: Session, message: str):
    """`claude -p`를 실행하고 나오는 stream-json을 이벤트로 바꿔 흘려보낸다."""
    if not CLAUDE_BIN:
        yield ("error", "claude 명령을 찾지 못했습니다.")
        return

    cmd = [
        CLAUDE_BIN,
        "-p",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--model", MODEL,
        "--permission-mode", PERMISSION_MODE,
    ]
    if session.cli_session_id:
        cmd += ["--resume", session.cli_session_id]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ASSISTANT_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        yield ("error", f"claude 실행에 실패했습니다: {exc}")
        return

    with session.lock:
        session.proc = proc
        session.cancelled = False

    errbuf: list[str] = []
    threading.Thread(target=_drain, args=(proc.stderr, errbuf), daemon=True).start()

    try:
        proc.stdin.write(message)
        proc.stdin.close()
    except OSError:
        pass

    # 제한 시간이 지나면 프로세스를 끊는다.
    killer = threading.Timer(TIMEOUT, proc.terminate)
    killer.daemon = True
    killer.start()

    saw_text = False
    fallback = ""
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue

            kind = obj.get("type")

            if kind == "system":
                if obj.get("session_id"):
                    session.cli_session_id = obj["session_id"]

            elif kind == "stream_event":
                event = obj.get("event") or {}
                etype = event.get("type")
                if etype == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        saw_text = True
                        yield ("delta", delta["text"])
                elif etype == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        yield ("status", TOOL_LABELS.get(name, "작업하는 중"))

            elif kind == "assistant":
                for block in (obj.get("message") or {}).get("content") or []:
                    if block.get("type") == "text" and block.get("text"):
                        fallback += block["text"]

            elif kind == "result":
                if obj.get("session_id"):
                    session.cli_session_id = obj["session_id"]
                if isinstance(obj.get("result"), str):
                    fallback = fallback or obj["result"]
    finally:
        killer.cancel()
        code = proc.wait()
        with session.lock:
            cancelled = session.cancelled
            session.proc = None

    # 부분 스트리밍이 오지 않은 경우를 대비한 보루.
    if not saw_text and fallback.strip():
        yield ("delta", fallback)
        saw_text = True

    if cancelled:
        return
    if not saw_text:
        detail = "".join(errbuf).strip().splitlines()
        tail = detail[-1] if detail else f"종료 코드 {code}"
        yield ("error", f"응답을 받지 못했습니다. ({tail})")


# ------------------------------------------------------------- api 백엔드

def _system_prompt() -> str:
    """CLAUDE.md와 부서 문서를 하나로 이어 붙여 시스템 프롬프트로 쓴다."""
    parts = []
    persona = ASSISTANT_DIR / "CLAUDE.md"
    if persona.exists():
        parts.append(persona.read_text(encoding="utf-8"))
    for doc in sorted((ASSISTANT_DIR / "부서").glob("*.md")):
        parts.append(f"\n\n---\n\n# 부서 지침: {doc.stem}\n\n{doc.read_text(encoding='utf-8')}")
    parts.append(
        "\n\n---\n\n지금은 파일을 직접 읽거나 쓸 수 없는 채팅 전용 모드다. "
        "파일 작업이 필요하면 무엇을 만들지 설명하고 로지님께 확인받는다."
    )
    return "".join(parts)


def stream_api(session: Session, message: str):
    import anthropic

    client = anthropic.Anthropic()
    session.history.append({"role": "user", "content": message})
    collected = ""
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=8000,
            system=[{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}],
            messages=session.history,
        ) as stream:
            for text in stream.text_stream:
                if session.cancelled:
                    break
                collected += text
                yield ("delta", text)
    except anthropic.APIStatusError as exc:
        session.history.pop()
        yield ("error", f"Claude API 오류 ({exc.status_code}).")
        return
    except anthropic.APIConnectionError:
        session.history.pop()
        yield ("error", "Claude API에 연결하지 못했습니다.")
        return

    if collected:
        session.history.append({"role": "assistant", "content": collected})
    else:
        session.history.pop()


# ------------------------------------------------------------ demo 백엔드

DEMO_REPLIES = [
    (("시장", "경쟁", "조사", "리서치", "기획"), "전략기획실",
     "전략기획실로 배정했습니다. 요청하신 내용은 목적·현황·판단 순으로 정리해서 "
     "산출물/ 폴더에 문서로 남기겠습니다.\n지금은 데모 모드라 실제 조사는 하지 않습니다."),
    (("지출", "자산", "예산", "정산", "돈", "비용", "매출"), "재무관리팀",
     "재무관리팀으로 배정했습니다. 기준일과 단위를 붙여 항목별로 집계하고, "
     "계산식까지 함께 보여드리겠습니다.\n지금은 데모 모드라 실제 수치는 넣지 않았습니다."),
    (("메일", "문구", "카피", "공지", "글", "제목", "초안"), "카피라이팅실",
     "카피라이팅실로 배정했습니다. 받는 분과 목적을 정한 뒤 초안 2안과 제목 후보 3개를 "
     "올리겠습니다. 발송은 로지님 확인 후에 하겠습니다.\n지금은 데모 모드입니다."),
]

DEMO_DEFAULT = (
    "비서실장이 직접 처리하겠습니다. 다만 지금은 데모 모드라 실제 작업은 하지 않습니다.\n"
    "`claude` CLI를 설치하고 로그인하시면 마리코가 파일을 읽고 문서까지 만들어 드립니다."
)


def stream_demo(session: Session, message: str):
    text = DEMO_DEFAULT
    lowered = message.lower()
    for keywords, _dept, reply in DEMO_REPLIES:
        if any(k in lowered for k in keywords):
            text = reply
            break
    for chunk in text.split(" "):
        if session.cancelled:
            return
        yield ("delta", chunk + " ")
        time.sleep(0.04)


BACKENDS = {"cli": stream_cli, "api": stream_api, "demo": stream_demo}


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Mariko/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 접근 로그는 조용히
        pass

    # -- 응답 도우미 -------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    # -- 라우팅 ------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                body = INDEX_FILE.read_bytes()
            except OSError:
                self._send(500, b"index.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
        elif path == "/api/profile":
            profile = load_profile()
            profile["backend"] = BACKEND
            profile["model"] = MODEL if BACKEND != "demo" else None
            self._json(profile)
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/chat":
            self.handle_chat()
        elif path == "/api/stop":
            session = get_session(self._read_json().get("session"))
            session.cancel()
            self._json({"ok": True})
        elif path == "/api/reset":
            data = self._read_json()
            session = get_session(data.get("session"))
            session.cancel()
            with SESSIONS_LOCK:
                SESSIONS.pop(session.id, None)
            self._json({"ok": True})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    # -- 채팅 스트림 -------------------------------------------------

    def handle_chat(self):
        data = self._read_json()
        message = (data.get("message") or "").strip()
        session = get_session(data.get("session"))

        if not message:
            self._json({"error": "빈 메시지입니다."}, 400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        # 길이를 미리 알 수 없는 스트림이라 연결을 닫아 끝을 알린다.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        def emit(event: str, payload) -> None:
            chunk = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()

        with session.lock:
            session.cancelled = False

        emit("open", {"session": session.id, "backend": BACKEND})

        # 백엔드는 별도 스레드에서 돌리고, 큐로 받아 흘려보낸다.
        # 그래야 응답이 없는 동안에도 주기적으로 신호를 보내 연결을 지킬 수 있다.
        events: queue.Queue = queue.Queue()

        def run():
            try:
                for event, payload in BACKENDS[BACKEND](session, message):
                    events.put((event, payload))
            except Exception as exc:  # 백엔드가 죽어도 채팅창은 살려 둔다
                events.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                events.put((None, None))

        worker = threading.Thread(target=run, daemon=True)
        worker.start()

        try:
            while True:
                try:
                    event, payload = events.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                if event is None:
                    break
                if event == "delta":
                    emit("delta", {"text": payload})
                elif event == "status":
                    emit("status", {"text": payload})
                elif event == "error":
                    emit("error", {"message": payload})
            emit("done", {"session": session.id})
        except (BrokenPipeError, ConnectionResetError):
            # 채팅창이 닫혔거나 멈춤을 눌렀다. 돌던 작업도 같이 끊는다.
            session.cancel()


def main() -> None:
    if not ASSISTANT_DIR.is_dir():
        sys.exit(f"[마리코] 비서 폴더가 없습니다: {ASSISTANT_DIR}")

    profile = load_profile()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True

    note = {
        "cli": f"claude CLI · {MODEL} · 권한 {PERMISSION_MODE}",
        "api": f"Claude API · {MODEL}",
        "demo": "데모 모드 — 정해진 문구로만 답합니다",
    }[BACKEND]

    print(f"  {profile.get('name')} · {profile.get('title')}")
    print(f"  {note}")
    if BACKEND == "demo":
        print("  claude 명령을 찾지 못했습니다. Claude Code를 설치하고 로그인하면")
        print("  마리코가 실제로 일합니다:  npm install -g @anthropic-ai/claude-code")
        print("  설치돼 있는데도 이 문구가 보이면:  MARIKO_CLAUDE_BIN=$(which claude) python3 server.py")
    print(f"  http://{HOST}:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
