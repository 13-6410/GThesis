"""
test4.py
QWERTY / QWERTZ / Dvorak / Colemak の入力効率シミュレーション (test3.py の改善版)

test3.py からの変更点:
  1. 距離計算を「ホームポジション基準(home_model)」から
     「各指の直前の打鍵位置からの移動を積算する chain_model」に変更した。
     (例: QWERTYで "bridge" の b→r はどちらも左手人差し指だが、
      home_model は (home→b) + (home→r) を計上してしまい、
      実際の (home→b) + (b→r) より不自然に大きくなっていた。
      同一キー連打(例: "ss")でも同様に、2打目は本来ほぼ移動0のはずが
      home_model では毎回ホームからの距離を計上してしまっていた)
  2. home_model は撤去し、chain_model の値のみを DistanceTotal /
     DistanceAverage として出力する。

本研究で意図的に対応していない前提(方法・考察に明記する想定):
  - Shift操作のコスト: inputEN.txt も大文字化して扱い、大文字/小文字混在時の
    Shiftキー入力のコストはモデル化していない
  - 座標系: 実機のメーカー・シリーズごとの物理配置差や段差(3次元的な動き)は
    再現せず、計算しやすい理想的な平面グリッド座標を採用している
  - 指ごとの打鍵速度差: 人差し指〜小指の速度差は距離計算には反映していない
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

BASE_DIR = Path(__file__).resolve().parent
TEXT_DIR = BASE_DIR / "Text"
LAYOUT_DIR = BASE_DIR / "KeyLayout"
RESULTS_DIR = BASE_DIR / "Results"

TEXT_FILENAMES = ["inputJP.txt", "inputEN.txt", "inputDE.txt", "inputES.txt"]


def load_text(filename: str) -> str | None:
    path = TEXT_DIR / filename
    if not path.exists():
        print(f"[WARN] テキストファイルが見つかりません: {path}")
        return None
    return path.read_text(encoding="utf-8").upper()


def load_layout(json_path: Path):
    with open(json_path, encoding="utf-8") as f:
        layout_data = json.load(f)

    layout = layout_data.get("KeyLayout") or layout_data.get("KeyLeyout")
    if layout is None:
        raise KeyError(f'"KeyLayout" / "KeyLeyout" キーが見つかりません: {json_path}')

    homepos = layout_data["HomePosition"]

    home_coords = {}
    for finger_id, home_key in homepos.items():
        key_data = layout[home_key]
        home_coords[finger_id] = (key_data["x"], key_data["y"])

    return layout, home_coords


def euclidean_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def analyze_layout(layout_path: Path, text: str, allowed_chars: set[str] | None) -> dict:
    """1つのレイアウト×1つのテキストを解析して集計結果を返す(chain_model版)"""

    layout, home_coords = load_layout(layout_path)

    # 各指の「現在位置」。最初は全指ホームポジションにあるとする
    finger_pos = dict(home_coords)

    valid_chars = 0
    skipped_chars: dict[str, int] = {}

    distance_total = 0.0
    same_hand_count = 0
    same_finger_count = 0
    same_key_count = 0

    prev_char = None

    for ch in text:
        if allowed_chars is not None and ch not in allowed_chars:
            continue

        if ch not in layout:
            skipped_chars[ch] = skipped_chars.get(ch, 0) + 1
            continue

        valid_chars += 1

        key = layout[ch]
        finger_id = f"{key['hand']}_{key['finger']}"
        cur_pos = (key["x"], key["y"])

        # その指が直前にいた位置(初回はホームポジション)からの移動距離を積算し、
        # 位置を更新する -> 同じ指が連続する場合は「直前キー→今回のキー」になる
        distance_total += euclidean_distance(finger_pos[finger_id], cur_pos)
        finger_pos[finger_id] = cur_pos

        if prev_char is not None and prev_char in layout:
            prev = layout[prev_char]
            curr = key

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
        "SameHandRate": same_hand_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
        "SameFingerRate": same_finger_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
        "SameKeyRate": same_key_count / (valid_chars - 1) if valid_chars > 1 else 0.0,
    }


def common_chars_across_layouts(layout_paths: list[Path], text: str) -> set[str]:
    """全レイアウトに共通して存在する文字だけを対象にするための集合を求める"""
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
                f"dist_total={result['DistanceTotal']:>10.1f} "
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
