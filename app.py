"""Web entry point for the SHG calculator."""
from pathlib import Path

from flask import Flask, redirect, request, send_from_directory
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from shg.model import calculate, defaults

PUBLIC = Path(__file__).resolve().parent / 'public'
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 65536


@app.get('/')
def home():
    return redirect('/index.html')


@app.get('/<path:filename>')
def local_asset(filename):
    # Local Flask preview. Vercel serves public/ files from its CDN.
    return send_from_directory(PUBLIC, filename)


@app.get('/api/bootstrap')
def bootstrap():
    return {'defaults': defaults(), 'result': calculate({}, include_baseline_maps=False)}


@app.errorhandler(RequestEntityTooLarge)
def payload_too_large(_error):
    return {'error': '参数长度不正确。'}, 413


@app.post('/api/calculate')
def recalculate():
    if not request.is_json:
        return {'error': '请输入 JSON 格式的参数。'}, 415
    try:
        payload = request.get_json()
    except BadRequest:
        return {'error': 'JSON 参数格式错误。'}, 400
    try:
        return calculate(payload, include_baseline_maps=False)
    except (ValueError, TypeError) as error:
        return {'error': str(error)}, 400
