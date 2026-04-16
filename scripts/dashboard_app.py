#!/usr/bin/env python
"""Small Flask dashboard to view alerts, analytics, and upload queue.

Run: `py -u scripts/dashboard_app.py` and open http://localhost:5000

Requires Flask (`pip install flask`).
"""
from pathlib import Path
import json
from flask import Flask, jsonify, render_template_string
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.utils import PROJECT_ROOT

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>AIJapan Dashboard</title></style></head>
<body>
<h1>AIJapan Dashboard</h1>
<h2>Experiment Alerts</h2>
<pre id="alerts">Loading...</pre>
<h2>Upload Queue</h2>
<pre id="queue">Loading...</pre>
<h2>Analytics (latest)</h2>
<pre id="analytics">Loading...</pre>
<script>
async function load(){
  const a = await fetch('/api/alerts').then(r=>r.json());
  document.getElementById('alerts').textContent = JSON.stringify(a, null, 2);
  const q = await fetch('/api/queue').then(r=>r.json());
  document.getElementById('queue').textContent = JSON.stringify(q, null, 2);
  const an = await fetch('/api/analytics').then(r=>r.json());
  document.getElementById('analytics').textContent = JSON.stringify(an, null, 2);
}
load();
setInterval(load, 15000);
</script>
</body>
</html>
"""


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {"error": "invalid json"}


@app.route('/')
def index():
    return render_template_string(TEMPLATE)


@app.route('/api/alerts')
def api_alerts():
    p = PROJECT_ROOT / 'output' / 'experiment_alerts.json'
    return jsonify(load_json(p))


@app.route('/api/queue')
def api_queue():
    p = PROJECT_ROOT / 'output' / 'upload_queue.json'
    return jsonify(load_json(p))


@app.route('/api/analytics')
def api_analytics():
    p = PROJECT_ROOT / 'output' / 'analytics_report.json'
    return jsonify(load_json(p))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
