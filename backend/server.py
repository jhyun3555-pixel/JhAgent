import argparse
import json
import mimetypes
import os
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from backend.analytics import snapshot, create_report, get_report, csv_report, html_report
from backend.catalog import AGENTS, DOMAINS, EVENTS, SCENARIOS, EVENT_FLOW, CAMPAIGN_FLOW
from backend.database import Database
from backend.engine import Engine

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                if key.strip() in ('AGENT_PROVIDER', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'PORT', 'AGENT_STEP_DELAY', 'AGENT_TIMEOUT'):
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def make_handler(db, engine, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def send(self, data, status=200, mime='application/json; charset=utf-8', filename=None):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False)
            raw = data.encode('utf-8') if isinstance(data, str) else data
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            # Rejected requests may still have unread bodies. Do not reuse that
            # connection, or the body can be parsed as the next HTTP method.
            if status >= 400:
                self.close_connection = True
                self.send_header('Connection', 'close')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                self.send({'error': '허용되지 않은 호스트'}, 403)
                return
            parsed = urlparse(self.path)
            path, qs = parsed.path, parse_qs(parsed.query)
            try:
                if path == '/api/health':
                    self.send({'ok': True, 'version': '1.0.0', 'database': 'sqlite', 'provider': os.getenv('AGENT_PROVIDER', 'demo')})
                elif path == '/api/bootstrap':
                    self.send({'csrf_token': token, 'scenarios': SCENARIOS, 'domains': DOMAINS, 'events': EVENTS, 'event_flow': EVENT_FLOW, 'campaign_flow': CAMPAIGN_FLOW, 'customers': db.customers(), 'snapshot': snapshot(db, engine)})
                elif path in ('/api/snapshot', '/api/stream'):
                    minutes = int(qs.get('minutes', ['15'])[0])
                    if minutes not in (5, 15, 60, 1440):
                        raise ValueError('지원하지 않는 시간 범위입니다.')
                    if path == '/api/stream':
                        self.stream(minutes)
                    else:
                        self.send(snapshot(db, engine, minutes))
                elif path == '/api/jobs':
                    self.send(snapshot(db, engine, 1440)['jobs'])
                elif path.startswith('/api/jobs/'):
                    self.send(db.job(path.split('/')[-1]))
                elif path == '/api/reports':
                    self.send(db.rows('SELECT id,title,created_at FROM reports ORDER BY created_at DESC'))
                elif path.startswith('/api/reports/'):
                    part = path.split('/')[-1]
                    rid, _, ext = part.partition('.')
                    report = get_report(db, rid)
                    if ext == 'csv':
                        self.send(csv_report(report), mime='text/csv; charset=utf-8', filename=rid + '.csv')
                    elif ext == 'html':
                        self.send(html_report(report), mime='text/html; charset=utf-8')
                    else:
                        self.send(report)
                elif path == '/api/audit':
                    self.send(db.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 500'))
                else:
                    asset = (ROOT / 'frontend' / (path.lstrip('/') or 'index.html')).resolve()
                    if not asset.is_relative_to(ROOT / 'frontend') or not asset.is_file():
                        self.send({'error': '페이지를 찾을 수 없습니다.'}, 404)
                    else:
                        mime = mimetypes.guess_type(str(asset))[0] or 'application/octet-stream'
                        self.send(asset.read_bytes(), mime=mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
            except (ValueError, KeyError) as error:
                self.send({'error': str(error).strip("'")}, 404 if isinstance(error, KeyError) else 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send({'error': '서버에서 요청을 처리하지 못했습니다.'}, 500)

        def do_POST(self):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), token):
                self.send({'error': '페이지를 새로고침하고 다시 시도하세요.'}, 403)
                return
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                self.send({'error': '허용되지 않은 요청 출처'}, 403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('요청 크기는 16KB 이하여야 합니다.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('JSON 객체가 필요합니다.')
                path = urlparse(self.path).path
                if path == '/api/jobs':
                    jid = engine.submit(data, key=self.headers.get('Idempotency-Key'))
                    self.send({'id': jid}, 201)
                elif path.startswith('/api/jobs/'):
                    parts = path.split('/')
                    if len(parts) != 5:
                        raise ValueError('잘못된 작업 경로입니다.')
                    jid, action = parts[3:]
                    if action == 'decision':
                        engine.decide(jid, data.get('action'), data.get('consent', False))
                    elif action == 'cancel':
                        engine.cancel(jid)
                    elif action == 'retry':
                        engine.retry(jid)
                    else:
                        raise ValueError('지원하지 않는 작업입니다.')
                    self.send({'id': jid, 'ok': True})
                elif path == '/api/demo':
                    engine.set_demo(data.get('enabled'))
                    self.send({'enabled': engine.demo_until > time.time()})
                elif path == '/api/reports':
                    self.send(create_report(db, data.get('days', 7)), 201)
                    engine.notify()
                else:
                    self.send({'error': '경로를 찾을 수 없습니다.'}, 404)
            except (ValueError, KeyError, TypeError) as error:
                self.send({'error': str(error).strip("'")}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send({'error': '서버에서 요청을 처리하지 못했습니다.'}, 500)

        def stream(self, minutes):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            try:
                while not engine.closed:
                    payload = json.dumps(snapshot(db, engine, minutes), ensure_ascii=False)
                    self.wfile.write(('event: snapshot\ndata: ' + payload + '\n\n').encode())
                    self.wfile.flush()
                    with engine.changed:
                        engine.changed.wait(timeout=2)
                    time.sleep(.12)
            except (BrokenPipeError, ConnectionResetError):
                pass
    return Handler


def main():
    load_env()
    parser = argparse.ArgumentParser(description='Neutech Agent Operations')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8765')))
    parser.add_argument('--db', default=str(ROOT / 'data' / 'neutech.db'))
    parser.add_argument('--no-seed-history', action='store_true')
    args = parser.parse_args()
    db = Database(args.db)
    db.seed_customers()
    engine = Engine(db)
    if not args.no_seed_history:
        engine.seed_history()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(db, engine, secrets.token_urlsafe(32)))
    server.daemon_threads = True
    print(f'Neutech Agent Operations → http://127.0.0.1:{args.port}', flush=True)
    print('가상 고객 240명 · 독립 agent 10개 · 외부 발송 없음', flush=True)
    try:
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        server.server_close()


if __name__ == '__main__':
    main()
