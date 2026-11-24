"""Offline localhost UI, packaged with Python/numpy; no external service."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import traceback
import webbrowser

from shg.model import calculate, defaults

ROOT = Path(__file__).resolve().parents[1]
TOKEN = secrets.token_urlsafe(24)
CALC_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, body, content_type='application/json; charset=utf-8', status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/bootstrap':
            self.send({'token': TOKEN, 'defaults': defaults(), 'result': calculate({})})
        elif self.path in ('/', '/index.html', '/app.js', '/style.css'):
            name = 'index.html' if self.path == '/' else self.path[1:]
            mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
            self.send((ROOT/'public'/name).read_bytes(), mime+'; charset=utf-8')
        else:
            self.send({'error': '未找到页面。'}, status=404)

    def do_POST(self):
        if self.headers.get('X-App-Token') != TOKEN:
            self.send({'error': '请从程序打开的页面进行操作。'}, status=403)
            return
        if self.path != '/api/calculate':
            self.send({'error': '未找到操作。'}, status=404)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 65536:
                raise ValueError('参数长度不正确。')
            payload = json.loads(self.rfile.read(size))
            with CALC_LOCK:
                result = calculate(payload)
            self.send(result)
        except (ValueError, TypeError) as error:
            self.send({'error': str(error)}, status=400)
        except Exception:
            self.server.last_error = traceback.format_exc()
            self.send({'error': '计算未完成。请检查输入；错误详情已保存在程序启动窗口的诊断信息中。'}, status=500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true', help='For automated local checks only')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--check-gui', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.last_error = ''
    url = f'http://127.0.0.1:{server.server_port}/'
    if args.ready_file:
        args.ready_file.write_text(json.dumps({'url': url}), encoding='utf-8')
    if args.headless:
        server.serve_forever()
        return
    import tkinter as tk
    from tkinter import messagebox
    from tkinter import ttk
    window = tk.Tk()
    if args.check_gui:
        window.withdraw()
    window.title('NbOCl₂ 堆叠 SHG')
    window.geometry('440x210')
    window.resizable(False, False)
    ttk.Label(window, text='NbOCl₂ / hBN / NbOCl₂ 反射 SHG', font=('Microsoft YaHei', 12)).pack(pady=(22, 10))
    ttk.Label(window, text='计算页面已在浏览器中打开。\n使用结束后，关闭此窗口即可退出程序。', justify='center').pack(pady=6)
    ttk.Button(window, text='重新打开计算页面', command=lambda: webbrowser.open(url)).pack(pady=8)
    def diagnostics():
        messagebox.showinfo('诊断信息', server.last_error or '当前没有记录到计算错误。')
    ttk.Button(window, text='诊断信息', command=diagnostics).pack()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    window.after(250, window.destroy if args.check_gui else lambda: webbrowser.open(url))
    window.mainloop()
    server.shutdown()
    server.server_close()
    if args.check_gui and args.ready_file:
        args.ready_file.write_text(json.dumps({'gui_initialized_and_closed': True, 'url': url}), encoding='utf-8')


if __name__ == '__main__':
    main()
