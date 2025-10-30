#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#解析csv格式的蓝牙数据包，结合时间轴，输出特定时间点附近的控制命令写入情况
import csv, struct, datetime as dt
from pathlib import Path

CSV_COLS = ["time","conn_handle","peer_addr","dir","op","att_handle","uuid","value"]
CTRL_HANDLE = "0x0025"  # FFF1
NOTIF1 = "0x0028"       # FFF2
NOTIF2 = "0x002C"       # FFF3

# 你的录屏在 21:35:03 开始
BASE = dt.datetime.strptime("Oct 29 21:35:03.000", "%b %d %H:%M:%S.%f")

# 把“分:秒”转绝对时间（相对于 BASE）
def abs_time(minute:int, second:float) -> dt.datetime:
    # 这里 minute=35/36/37 等
    hh = 21
    return dt.datetime.strptime(f"Oct 29 {hh}:{minute:02d}:{second:06.3f}", "%b %d %H:%M:%S.%f")

# 你的时间轴（分钟,秒, 业务注释）
TIMELINE = [
    (35,  3.0,  "开始录屏"),
    (35, 16.0,  "打开蓝牙"),
    (35, 21.0,  "打开App"),
    (35, 28.0,  "Gain=-40.0 dB"),
    (35, 32.0,  "Gain=-20.6 dB"),
    (35, 37.0,  "Gain=  0.0 dB"),
    (35, 44.0,  "SHS=40%"),
    (35, 48.0,  "SHS=70%"),
    (35, 50.0,  "SHS=100%"),
    (35, 54.0,  "Delay=2.5 ms"),
    (35, 58.0,  "Delay=30.1 ms"),
    (36,  3.0,  "Delay=65 ms"),
    (36,  6.0,  "Phase=10 Hz"),
    (36, 11.0,  "Phase=320 Hz"),
    (36, 14.0,  "Phase=30000 Hz"),
    (36, 19.0,  "Phase=750 Hz"),
    (36, 25.0,  "Limiter开"),
    (36, 26.0,  "Limiter关"),
    (36, 27.0,  "Limiter再开"),
    (36, 28.0,  "进入Limiter设置页"),
    (36, 30.0,  "Attack=1"),
    (36, 40.0,  "Attack=3792"),
    (36, 50.0,  "Attack=8686"),
    (36, 55.0,  "Decay=1"),
    (36, 57.0,  "Decay=71"),
    (36, 58.5,  "Decay=128"),
    (36, 59.0,  "Pregain=-20.0 dB"),
    (36, 59.5,  "Pregain=-0.7 dB"),
    (37,  0.0,  "Pregain=+20.0 dB（至 37:00）"),
]

# 在时间 t 附近 ±window 秒的写入
def in_window(ts: dt.datetime, t: dt.datetime, window=1.2):
    return abs((ts - t).total_seconds()) <= window

def hex_to_bytes(s:str) -> bytes:
    s = (s or "").strip()
    if s=="":
        return b""
    if len(s)%2==1: s="0"+s
    return bytes.fromhex(s)

def u16le(b:bytes) -> int: return int.from_bytes(b[:2], "little")
def u32le(b:bytes) -> int: return int.from_bytes(b[:4], "little")

def f32le(b:bytes) -> float|None:
    if len(b)<4: return None
    try: return struct.unpack("<f", b[:4])[0]
    except: return None

def classify(b:bytes) -> str:
    if b.startswith(b"\x4D\x00\x00\x04\x80\x00"): return "SET_FREQ_A"
    if b.startswith(b"\x00\x08\x00"): return "SET_FLOAT_A"
    if b.startswith(b"\x00\x1B\x00"): return "SET_FLOAT_B"
    if b.startswith(b"\x00\x4C\x00\x00"): return "SELECT_SLOT"
    return "OTHER"

def decode(b:bytes) -> dict:
    kind = classify(b)
    out = {"kind":kind, "raw":b.hex()}
    if kind=="SET_FREQ_A":
        body = b[6:]
        freq16 = u16le(body) if len(body)>=2 else None
        freq32 = u32le(body) if len(body)>=4 else None
        hz = None
        if freq16 and 5 <= freq16 <= 40000:
            hz = float(freq16)
        elif freq32 and 1000 <= freq32 <= 200000:
            hz = round(freq32/100.0, 2)  # 假设 ×100
        out.update({"freq16":freq16, "freq32":freq32, "hz":hz, "tail":hex(b[-1])})
    elif kind in ("SET_FLOAT_A","SET_FLOAT_B"):
        # 可能出现导出缺字节，这里尝试两种修复
        tail = b[3:]
        val = f32le(tail)
        if val is None and len(tail)==3:
            # 常见缺高位：猜 0x3F/0x40
            for hi in (0x3F,0x40):
                try:
                    val = struct.unpack("<f", bytes([hi])+tail)[0]
                    break
                except: pass
        out["f32"] = val
    elif kind=="SELECT_SLOT":
        out["slot"] = u16le(b[4:6]) if len(b)>=6 else None
    return out

def parse_time(s:str) -> dt.datetime:
    # e.g., "Oct 29 21:34:24.827"
    return dt.datetime.strptime(s, "%b %d %H:%M:%S.%f")

def main(csv_path:str):
    rows=[]
    with open(csv_path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            if not all(k in r for k in CSV_COLS): continue
            try:
                r["_ts"] = parse_time(r["time"])
            except:
                continue
            rows.append(r)

    # 只看 CTRL 写入
    writes = [r for r in rows if r["dir"]=="Send" and r["op"].startswith("Write") and r["att_handle"]==CTRL_HANDLE]

    print("对齐报告（每个时间点 ±1.2s 内的 CTRL 写入）")
    print("="*72)
    for mm,ss,label in TIMELINE:
        t = abs_time(mm, ss)
        hits = [r for r in writes if in_window(r["_ts"], t, window=1.2)]
        print(f"\n[{mm:02d}:{ss:05.2f}] {label}  窗口命中 {len(hits)} 条")
        for r in hits:
            b = hex_to_bytes(r["value"])
            info = decode(b)
            print(f"  {r['time']}  {r['uuid']}  {info}")

if __name__=="__main__":
    import sys
    if len(sys.argv)<2:
        print("Usage: python report_by_timeline.py path/to/pklg_for_nomal.csv")
    else:
        main(sys.argv[1])