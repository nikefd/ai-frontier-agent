"""Loopback-only Anthropic-compatible capture bridge for a newly authorized exercise."""
from __future__ import annotations
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from app.storage import write_json_atomic

LIMIT=8*1024*1024

class LearningHttpCapture:
    def __init__(self, provider: dict, destination: Path):
        parsed=urlsplit(provider['ANTHROPIC_BASE_URL'])
        if parsed.scheme!='https' or parsed.hostname!='api.deepseek.com' or parsed.query or parsed.fragment:
            raise ValueError('HTTP capture only supports the official HTTPS DeepSeek endpoint')
        self.upstream=provider['ANTHROPIC_BASE_URL'].rstrip('/')
        self.key=provider['ANTHROPIC_API_KEY'];self.destination=destination
        self.prefix='/'+secrets.token_urlsafe(24);self.lock=threading.Lock();self.count=0
        capture=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_POST(self):
                path=self.path.split('?',1)[0]
                if path not in {capture.prefix+'/v1/messages',capture.prefix+'/v1/messages/count_tokens'}:
                    self.send_error(404);return
                try:length=int(self.headers.get('Content-Length','0'))
                except ValueError:length=0
                if not 0<length<=LIMIT:self.send_error(413);return
                try:body=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeDecodeError):self.send_error(400);return
                with capture.lock:capture.count+=1;number=capture.count
                target=capture.destination/f'exchange-{number:03d}.json'
                record={'sequence':number,'path':path[len(capture.prefix):],'started_at':time.time(),'request':body,'status':None,'response':'','complete':False}
                write_json_atomic(target,record)
                headers={k:self.headers[k] for k in ('anthropic-version','anthropic-beta','content-type','accept') if self.headers.get(k)}
                headers['x-api-key']=capture.key
                try:
                    with httpx.Client(timeout=httpx.Timeout(240,connect=20),trust_env=False,follow_redirects=False) as client:
                        with client.stream('POST',capture.upstream+record['path'],headers=headers,json=body) as response:
                            record['status']=response.status_code
                            self.send_response(response.status_code)
                            self.send_header('Content-Type',response.headers.get('content-type','application/json'))
                            self.send_header('Connection','close');self.end_headers()
                            chunks=[];size=0
                            try:
                                for chunk in response.iter_bytes():
                                    size+=len(chunk)
                                    if size>LIMIT:raise ValueError('Response exceeds capture limit')
                                    chunks.append(chunk);self.wfile.write(chunk);self.wfile.flush()
                                record['complete']=True
                            finally:record['response']=b''.join(chunks).decode('utf-8',errors='replace')
                except (httpx.HTTPError,OSError,ValueError) as error:
                    record['error_type']=type(error).__name__
                finally:
                    record['duration_ms']=round((time.time()-record['started_at'])*1000)
                    write_json_atomic(target,record);self.close_connection=True
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):
        self.destination.mkdir(parents=True,exist_ok=True);self.thread.start();return self
    @property
    def base_url(self):return f'http://127.0.0.1:{self.server.server_port}'+self.prefix
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
