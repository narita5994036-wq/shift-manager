#!/usr/bin/env python3
"""
shift PDF → JSON extractor
Usage: python3 extract_shifts.py shift_YYYY-MM.pdf
Output: data/shifts_YYYY-MM.json
"""

import sys, re, zlib, json, os
from pathlib import Path

# PDF の英字名 → アプリのメンバー名マッピング
NAME_MAP = {
    "narita":    "成田",
    "shoda":     "正田",
    "otani":     "尾谷",
    # 必要に応じて追加
}

def decode_pdf_str(b):
    return ''.join(chr(c) for c in b if c != 0 and 0x20 <= c <= 0x7E)

def extract_entries(pdf_path):
    with open(pdf_path, 'rb') as f:
        data = f.read()

    streams = []
    for m in re.finditer(b'stream\r?\n', data):
        start = m.end()
        end = data.find(b'endstream', start)
        if end == -1: continue
        try:
            streams.append(zlib.decompress(data[start:end].strip()))
        except:
            pass

    if not streams:
        raise ValueError("PDF からストリームを展開できませんでした")

    # 最大のストリームをコンテンツとして使用
    raw = max(streams, key=len)
    entries = []
    px, py = 0.0, 0.0
    for block in re.findall(rb'BT(.*?)ET', raw, re.DOTALL):
        px, py = 0.0, 0.0
        for line in block.split(b'\n'):
            line = line.strip()
            tm = re.match(rb'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+Tm', line)
            if tm: px, py = float(tm.group(5)), float(tm.group(6))
            td = re.match(rb'(-?[\d.]+)\s+(-?[\d.]+)\s+Td', line)
            if td: px += float(td.group(1)); py += float(td.group(2))
            tj = re.search(rb'\((.*?)\)\s*Tj', line)
            if tj:
                entries.append((round(py, 1), round(px, 1), decode_pdf_str(tj.group(1))))
    return entries

def build_day_map(entries):
    """y≈518-519 行から日付 → x座標マップを構築"""
    # 最初に日付行のy座標を検出（1〜31の数字が連続して並ぶ行）
    y_candidates = {}
    for y, x, t in entries:
        t = t.strip()
        try:
            n = int(t)
            if 1 <= n <= 31:
                yk = round(y)
                y_candidates.setdefault(yk, []).append((x, n))
        except:
            pass

    # 最も多くの日付を含む行を選択
    best_y = max(y_candidates, key=lambda k: len(y_candidates[k]), default=None)
    if best_y is None or len(y_candidates[best_y]) < 20:
        raise ValueError("日付ヘッダー行が見つかりません")

    day_x = {n: x for x, n in y_candidates[best_y]}
    return best_y, day_x

def nearest_day(x, x_day):
    return x_day[min(x_day.keys(), key=lambda k: abs(k - x))]

def detect_employees(entries):
    """英字名（姓 名 形式）の行を検出してy座標とマッピングを返す"""
    employees = []
    for y, x, t in entries:
        if x > 100: continue
        # 非アルファベット文字を除去、小文字→大文字の境界にスペースを挿入
        cleaned = re.sub(r'[^A-Za-z ]', ' ', t)
        cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned).strip()
        parts = cleaned.split()
        # 2単語以上、各単語が大文字始まり
        if len(parts) >= 2 and all(p[0].isupper() for p in parts if p):
            last = parts[0].lower()
            jp_name = NAME_MAP.get(last)
            if jp_name:
                employees.append((y, jp_name))
    return employees

def find_time_rows(entries, name_y, day_header_y):
    """名前行の近くにある時刻行（開始・終了）を検出
    PDFのy座標は下から上に増加するため:
      開始時刻行 = name_y より少し上 (y値が大きい)
      終了時刻行 = name_y より少し下 (y値が小さい)
    """
    WINDOW = 8  # 名前行から±8以内のみ検索
    time_rows = []
    for y, x, t in entries:
        if abs(y - name_y) > WINDOW: continue
        if abs(y - name_y) < 0.5: continue  # 名前行自体は除外
        if re.match(r'^\d{2}:\d{2}$', t.strip()):
            time_rows.append((y, x, t.strip()))

    if not time_rows:
        return None, None

    y_groups = {}
    for y, x, t in time_rows:
        yk = round(y, 1)
        y_groups.setdefault(yk, []).append((x, t))

    if len(y_groups) < 2:
        return None, None

    # 上側 (y大) = 開始時刻、下側 (y小) = 終了時刻
    sorted_ys = sorted(y_groups.keys(), reverse=True)
    start_y = sorted_ys[0]
    end_y   = sorted_ys[1]
    return {x: t for x, t in y_groups[start_y]}, {x: t for x, t in y_groups[end_y]}

def make_shift_obj(start, end):
    return {"status": "出勤", "startTime": start, "endTime": end, "breakTime": 60, "memo": ""}

def make_off_obj():
    return {"status": "休日", "startTime": "", "endTime": "", "breakTime": 60, "memo": ""}

def extract(pdf_path):
    entries = extract_entries(pdf_path)
    header_y, day_x = build_day_map(entries)
    x_day = {x: d for d, x in day_x.items()}

    # 月・年をファイル名から取得
    stem = Path(pdf_path).stem  # shift_2026-04
    m = re.search(r'(\d{4})-(\d{2})', stem)
    if not m:
        raise ValueError(f"ファイル名から年月を取得できません: {stem}")
    year, month = int(m.group(1)), int(m.group(2))

    import calendar
    days_in_month = calendar.monthrange(year, month)[1]

    employees = detect_employees(entries)
    result = {}

    for name_y, jp_name in employees:
        starts_map, ends_map = find_time_rows(entries, name_y, header_y)
        if not starts_map:
            continue

        member_shifts = {}
        # 出勤日のデータを登録
        work_days = set()
        for x, t in starts_map.items():
            d = nearest_day(x, x_day)
            work_days.add(d)

        for d in range(1, days_in_month + 1):
            dk = f"{year}-{month:02d}-{d:02d}"
            if d in work_days:
                # 開始時刻を探す
                sx = min(starts_map.keys(), key=lambda k: abs(nearest_day(k, x_day) - d))
                ex = min(ends_map.keys(),   key=lambda k: abs(nearest_day(k, x_day) - d)) if ends_map else None
                s = starts_map.get(sx, "")
                e = ends_map.get(ex, "")   if ends_map else ""
                member_shifts[dk] = make_shift_obj(s, e)
            else:
                member_shifts[dk] = make_off_obj()

        result[jp_name] = member_shifts
        print(f"  {jp_name}: {len(work_days)}日出勤")

    return result, year, month

def main():
    # 引数指定があればそのファイル、なければ shift_*.pdf を全処理
    if len(sys.argv) > 1:
        pdfs = [sys.argv[1]]
    else:
        pdfs = sorted(Path('.').glob('shift_*.pdf'))
        if not pdfs:
            print("処理するPDFが見つかりません")
            sys.exit(1)

    os.makedirs('data', exist_ok=True)

    for pdf in pdfs:
        print(f"\n処理中: {pdf}")
        try:
            data, year, month = extract(str(pdf))
            out = Path('data') / f"shifts_{year}-{month:02d}.json"
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  → {out} に保存")
        except Exception as e:
            print(f"  エラー: {e}")

if __name__ == '__main__':
    main()
