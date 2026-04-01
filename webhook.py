#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import subprocess
import uvicorn
import hmac
import hashlib
import csv
import os
import asyncio

app = FastAPI()

SECRET = ""

# 统一管理多个 CSV
CSV_FILES = {
    "1": "/home/sli/Bifrost/base/worker/data/gcc_data_file.csv",
    "2": "/home/sli/Bifrost/worker/data/gcc_data_file.csv"
}


# ===========================================================
# Webhook（git pull）
# ===========================================================
def verify_signature(request_body: bytes, signature: str) -> bool:
    if not SECRET:
        return True
    if not signature:
        return False
    sha_name, sign = signature.split("=")
    mac = hmac.new(SECRET.encode(), msg=request_body, digestmod=hashlib.sha256)
    return hmac.compare_digest(sign, mac.hexdigest())


@app.post("/webhook")
async def webhook(request: Request):
    try:
        out = subprocess.check_output(["git", "-C", ".", "pull"], stderr=subprocess.STDOUT).decode()
        return {"status": "ok", "output": out}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "output": e.output.decode()}


# ===========================================================
# CSV 读取函数（通用）
# ===========================================================
def read_csv_rows(path):
    if not os.path.exists(path):
        return [], [], []
    ts, avail, sent = [], [], []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts.append(row["TimeStamp"])
            avail.append(float(row["AvailableBitrate0"]))
            sent.append(float(row["SentBitrate0"]))
    return ts, avail, sent


def file_mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


# ===========================================================
# 统一：图表数据接口
# ===========================================================
@app.get("/chart/{cid}/data")
async def chart_data(cid: str):
    path = CSV_FILES.get(cid)
    if not path:
        return {"error": "Invalid chart id"}
    ts, avail, sent = read_csv_rows(path)
    return {"timestamps": ts, "available": avail, "sent": sent}


# ===========================================================
# 统一：SSE 实时推送接口
# ===========================================================
@app.get("/chart/{cid}/stream")
async def chart_stream(cid: str):

    path = CSV_FILES.get(cid)
    if not path:
        return StreamingResponse(iter([]), media_type="text/event-stream")

    async def event_gen():
        last = file_mtime(path)
        while True:
            await asyncio.sleep(1)
            now = file_mtime(path)
            if now != last:
                last = now
                yield "data: update\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ===========================================================
# HTML 页面（统一模板）
# ===========================================================
@app.get("/chart/{cid}", response_class=HTMLResponse)
async def show_chart(cid: str):

    if cid not in CSV_FILES:
        return HTMLResponse("<h3>Invalid chart ID</h3>")

    title = f"Bitrate Chart (CSV {cid})"

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>

<h2 style="text-align:center;">{title}</h2>
<canvas id="chart" width="1600" height="600"></canvas>

<script>
let chart = null;

function drawChart(timestamps, available, sent) {{
    const data = {{
        labels: timestamps,
        datasets: [
            {{
                label: 'AvailableBitrate0',
                data: available,
                borderColor: 'blue',
                borderWidth: 2,
                fill: false
            }},
            {{
                label: 'SentBitrate0',
                data: sent,
                borderColor: 'orange',
                borderWidth: 2,
                fill: false
            }}
        ]
    }};
    if (chart) chart.destroy();
    chart = new Chart(document.getElementById('chart'), {{
        type: 'line',
        data: data
    }});
}}

async function loadData() {{
    const res = await fetch("/chart/{cid}/data");
    const json = await res.json();
    drawChart(json.timestamps, json.available, json.sent);
}}

loadData();

// SSE
const evt = new EventSource("/chart/{cid}/stream");
evt.onmessage = function(evt) {{
    if (evt.data === "update") {{
        console.log("CSV changed → refresh");
        loadData();
    }}
}};
</script>

</body>
</html>
"""
    return HTMLResponse(html)



# ===========================================================
# 启动服务
# ===========================================================
if __name__ == "__main__":
    uvicorn.run("webhook:app", host="0.0.0.0", port=8080, reload=False)
