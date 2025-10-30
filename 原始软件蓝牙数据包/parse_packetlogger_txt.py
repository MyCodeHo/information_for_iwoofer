'''
Author: zpw 980155872@qq.com
Date: 2025-10-28 10:30:23
LastEditors: zpw 980155872@qq.com
LastEditTime: 2025-10-28 10:30:48
FilePath: /helper/parse_packetlogger_txt.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# 用法:
#   python3 parse_packetlogger_txt.py input.txt out.csv
#
# 功能:
#   从 PacketLogger 的文本导出（.txt）中提取 BLE ATT 关键信息，输出 CSV：
#   time,conn_handle,peer_addr,dir,op,att_handle,uuid,value
#
# 说明:
#   - 解析 "ATT Send/ATT Receive" 行，提取:
#       * 时间戳（行首）
#       * 连接句柄 (0xNNNN)
#       * 对端地址 (MAC)
#       * 方向 (Send/Receive)
#       * 操作 (Write Request / Handle Value Notification / Write Response / Read By Type …)
#       * ATT 句柄 (Handle:0xNNNN)
#       * 特征 UUID 简写（如 FFF1/FFF2/FFF3/FFF4），若存在
#       * Value（十六进制，去空格）
#   - 同时粗略提取 MTU 交换、CCCD 配置等（没 Value 也会保留 op/handle/uuid 方便对照）
#
import re
import sys
import csv

if len(sys.argv) < 3:
    print("Usage: python3 parse_packetlogger_txt.py input.txt out.csv")
    sys.exit(1)

in_path = sys.argv[1]
out_path = sys.argv[2]

# 典型行示例：
# Oct 28 09:43:10.180  ATT Send         0x0041  F8:30:02:08:DF:00  Write Request - Handle:0x0025 - FFF1 - Value: 0000 0000 00
# Oct 28 09:43:10.237  ATT Receive      0x0041  F8:30:02:08:DF:00  Handle Value Notification - Handle:0x002C - FFF3 - Value: 0100 0000 ...
# Oct 28 09:43:09.189  ATT Send         0x0041  F8:30:02:08:DF:00  Exchange MTU Request - MTU: 185
# Oct 28 09:43:09.488  ATT Send         0x0041  F8:30:02:08:DF:00  Write Request - Handle: 0x000F - Service Changed - Configuration - Indication

# 时间 + ATT + 方向 + 连接 + 地址 + 剩余文本
line_re = re.compile(
    r"^(?P<time>[A-Z][a-z]{2}\s+\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+ATT\s+(?P<dir>Send|Receive)\s+"
    r"(?P<conn>0x[0-9A-Fa-f]{4})\s+(?P<addr>(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+(?P<rest>.+)$"
)

# 操作名（Write Request / Handle Value Notification 等）抓取
op_re = re.compile(r"^(?P<op>[^-]+?)(?:\s+-\s+|$)")
# 句柄
handle_re = re.compile(r"Handle:\s*0x([0-9A-Fa-f]{4})")
# UUID 简写（如 FFF1/FFF2/FFF3/FFF4）通常出现在 " - FFF1 - " 这类片段
uuid_re = re.compile(r"\s-\s([0-9A-Fa-f]{4})\s-")
# Value 抓取（允许空格分组）
value_re = re.compile(r"Value:\s*([0-9A-Fa-f]{2}(?:\s*[0-9A-Fa-f]{2})*)")

rows = []

with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        m = line_re.match(ln)
        if not m:
            continue
        time = m.group("time")
        dir_ = m.group("dir")
        conn = m.group("conn")
        addr = m.group("addr")
        rest = m.group("rest").strip()

        # 操作名
        opm = op_re.match(rest)
        op = opm.group("op").strip() if opm else ""

        # 句柄
        h = handle_re.search(rest)
        att_handle = f"0x{h.group(1)}" if h else ""

        # UUID（若存在）
        u = uuid_re.search(rest)
        uuid = u.group(1).upper() if u else ""

        # Value（若存在）
        v = value_re.search(rest)
        value = ""
        if v:
            # 去掉空格，转成连续十六进制
            value = "".join(v.group(1).split()).upper()

        rows.append([
            time, conn, addr, dir_, op, att_handle, uuid, value
        ])

# 写 CSV
with open(out_path, "w", newline="") as csvf:
    w = csv.writer(csvf)
    w.writerow(["time", "conn_handle", "peer_addr", "dir", "op", "att_handle", "uuid", "value"])
    w.writerows(rows)

print(f"Done. Wrote {len(rows)} rows to {out_path}")