import subprocess
import time
import csv
from datetime import datetime
import re
import os

# -------- 配置 ---------
IFACE = "eth0"                        # 网卡名称
INTERVAL = 0.2                        # 间隔 0.2s
CSV_FILE = "/home/sli/logs/qdisc_rq_log.csv"  # ←←← 指定你想要的绝对路径
# -----------------------

def read_qdisc_info(iface):
    """读取 tc -s qdisc 输出并解析各 fq_codel 队列的 limit/backlog."""
    try:
        output = subprocess.check_output(
            ["tc", "-s", "qdisc", "show", "dev", iface],
            stderr=subprocess.DEVNULL
        ).decode()
    except:
        return []

    lines = output.splitlines()
    results = []
    current_limit = None

    for line in lines:
        line = line.strip()

        # 找到 fq_codel 行，提取 limit
        if "fq_codel" in line and "limit" in line:
            m = re.search(r"limit (\d+)p", line)
            if m:
                current_limit = int(m.group(1))

        # 找到 backlog 行
        if "backlog" in line and current_limit is not None:
            m = re.search(r"backlog .*?(\d+)p", line)
            if m:
                backlog = int(m.group(1))
                rq = max(current_limit - backlog, 0)
                results.append((current_limit, backlog, rq))
                current_limit = None  # reset

    return results


def main():
    # 创建目录（如果不存在）
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

    print(f"开始记录 {IFACE} 队列状态，每 {INTERVAL}s...")
    print(f"写入文件: {CSV_FILE}")

    # 写入 CSV header
    header = ["TimeStamp"]
    for i in range(4):
        header += [f"limit{i}", f"backlog{i}", f"RQ{i}"]

    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        while True:
            timestamp = datetime.utcnow().isoformat()
            qdisc_info = read_qdisc_info(IFACE)

            # 构造一行
            row = [timestamp]
            for i in range(4):
                if i < len(qdisc_info):
                    limit, backlog, rq = qdisc_info[i]
                else:
                    limit, backlog, rq = 0, 0, 0
                row += [limit, backlog, rq]

            writer.writerow(row)
            f.flush()
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
