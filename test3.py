"""
test3.py
QWERTY / QWERTZ / Dvorak / Colemak の入力効率シミュレーション (test2.py の改善版)

test2.py からの変更点は末尾のコメント、または改善点の説明を参照。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import csv
from datetime import datetime

# ----------------------------
# 設定
# ----------------------------

# test2.py は実行時のカレントディレクトリ基準の相対パスだったため、
# スクリプト自身の場所を基準にすることでどこから実行しても動くようにする
BASE_DIR = Path(__file__).resolve().parent
TEXT_DIR = BASE_DIR / "Text"
LAYOUT_DIR = BASE_DIR / "KeyLayout"
RESULTS_DIR = BASE_DIR / "Results"

# test2.py は存在しない "input.txt" を参照していたため、実在するファイルを指定する
# 複数指定すると、それぞれについてレイアウト間比較を行う(日本語/英語の比較などに利用可能)
TEXT_FILENAMES = ["inputJP.txt", "inputEN.txt"]


def load_text(filename: str) -> str | None:
    path = TEXT_DIR / filename
    if not path.exists():
        print(f"[WARN] テキストファイルが見つかりません: {path}")
        return None
    return path.read_text(encoding="utf-8").upper()


def load_layout(json_path: Path):
    with open(json_path, encoding="utf-8") as f:
        layout_data = json.load(f)

    # JSON側のキー名が "KeyLeyout"(タイプミス)になっているため両対応させる
    layout = layout_data.get("KeyLayout") or layout_data.get("KeyLeyout")
    if layout is None:
        raise KeyError(f'"KeyLayout" / "KeyLeyout" キーが見つかりません: {json_path}')

    homepos = layout_data["HomePosition"]

    home_coords = {}
    for finger_id, home_key in homepos.items():
        key_data = layout[home_key]
        home_coords[finger_id] = (key_data["x"], key_data["y"])

    return layout, home_coords


def distance_from_home(layout: dict, home_coords: dict, ch: str) -> float:
    key = layout[ch]
    finger_id = f"{key['hand']}_{key['finger']}"
    hx, hy = home_coords[finger_id]
    dx = key["x"] - hx
    dy = key["y"] - hy
    return math.sqrt(dx * dx + dy * dy)


def analyze_layout(layout_path: Path, text: str, allowed_chars: set[str] | None) -> dict:
    """1つのレイアウト×1つのテキストを解析して集計結果を返す"""

    layout, home_coords = load_layout(layout_path)

    valid_chars = 0
    skipped_chars: dict[str, int] = {}

    distance_total = 0.0
    same_hand_count = 0
    same_finger_count = 0
    same_key_count = 0

    prev_char = None

    for ch in text:
        # 全レイアウトに共通する文字だけを対象にし、レイアウト間で母数を揃える
        if allowed_chars is not None and ch not in allowed_chars:
            continue

        if ch not in layout:
            skipped_chars[ch] = skipped_chars.get(ch, 0) + 1
            continue

        valid_chars += 1
        distance_total += distance_from_home(layout, home_coords, ch)

        if prev_char is not None and prev_char in layout:
            prev = layout[prev_char]
            curr = layout[ch]

            same_hand = prev["hand"] == curr["hand"]
            same_finger = same_hand and prev["finger"] == curr["finger"]
            same_key = prev_char == ch

            same_hand_count += same_hand
            same_finger_count += same_finger
            same_key_count += same_key

        prev_char = ch

    if skipped_chars:
        preview = ", ".join(f"{c!r}x{n}" for c, n in list(skipped_chars.items())[:10])
        print(f"[INFO] {layout_path.stem}: レイアウトに存在せずスキップした文字 -> {preview}")

    return {
        "Layout": layout_path.stem,
        "ValidChars": valid_chars,
        "DistanceTotal": round(distance_total, 4),
        "DistanceAverage": round(distance_total / valid_chars, 4) if valid_chars else 0.0,
        "SameHandCount": same_hand_count,
        "SameFingerCount": same_finger_count,
        "SameKeyCount": same_key_count,
        # test2.py は valid_chars <= 1 のとき ZeroDivisionError の可能性があったため三項式でガード
        "SameHandRate": same_hand_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
        "SameFingerRate": same_finger_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
        "SameKeyRate": same_key_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
    }


def common_chars_across_layouts(layout_paths: list[Path], text: str) -> set[str]:
    """全レイアウトに共通して存在する文字だけを対象にするための集合を求める
    (test2.py はこれをしておらず、レイアウトごとに valid_chars が異なり不公平な比較になっていた)"""
    common = set(text)
    for layout_path in layout_paths:
        layout, _ = load_layout(layout_path)
        common &= set(layout.keys())
    return common


def main():
    layout_paths = sorted(LAYOUT_DIR.glob("*.json"))
    if not layout_paths:
        print(f"[ERROR] キー配列 JSON が見つかりません: {LAYOUT_DIR}")
        return

    all_results = []

    for text_filename in TEXT_FILENAMES:
        text = load_text(text_filename)
        if text is None:
            continue

        allowed_chars = common_chars_across_layouts(layout_paths, text)

        print("=" * 60)
        print(f"Text source     : {text_filename}")
        print(f"共通対象文字種数: {len(allowed_chars)}")
        print("=" * 60)

        for layout_path in layout_paths:
            result = analyze_layout(layout_path, text, allowed_chars)
            result["TextSource"] = text_filename
            all_results.append(result)

            print(
                f"[{result['Layout']:<8}] "
                f"valid={result['ValidChars']:>6} "
                f"dist_avg={result['DistanceAverage']:.4f} "
                f"same_hand={result['SameHandRate']:.2%} "
                f"same_finger={result['SameFingerRate']:.2%} "
                f"same_key={result['SameKeyRate']:.2%}"
            )
        print()

    if not all_results:
        print("[ERROR] 解析できたテキストがありませんでした。TEXT_FILENAMES を確認してください。")
        return

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"{timestamp}.csv"

    fieldnames = [
        "TextSource", "Layout", "ValidChars", "DistanceTotal", "DistanceAverage",
        "SameHandCount", "SameFingerCount", "SameKeyCount",
        "SameHandRate", "SameFingerRate", "SameKeyRate",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)

    print(f"CSV saved : {csv_path}")


if __name__ == "__main__":
    main()
