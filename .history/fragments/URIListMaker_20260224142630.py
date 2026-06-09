import pandas as pd
import json
import glob
import os
import re

def ocr_to_rows(data, filename):
    """
    縦書き・右から左の読み順に特化した解析
    """
    # 1. ソートの実行
    # y[0] (Y座標) を降順: ページの上から下へ
    # y[1] (X座標) を降順: ページの右から左へ
    data.sort(key=lambda x: (-x[0], -x[1]))

    # 設定値（実際のデータを見て微調整が必要な場合があります）
    y_threshold = 60      # 同じ「行」とみなすY座標の許容範囲（ピクセル）
    x_border_right = 1650 # 「備考」と「読み」を分けるX座標の境界
    x_border_left = 1100  # 「読み」と「曲名」を分けるX座標の境界

    rows = []
    current_row_y = -1
    current_row = {"ページ": filename, "曲名": [], "読み": [], "備考": []}

    for item in data:
        y_min, x_min, y_max, x_max, text = item
        
        # 新しい「行」の判定
        # 直前の要素より一定以上Y座標が下がったら、新しい行とみなす
        if current_row_y == -1:
            current_row_y = y_min
        
        if y_min > current_row_y + y_threshold:
            # 既存の行を保存（何か中身があれば）
            if any(current_row[k] for k in ["曲名", "読み", "備考"]):
                rows.append({k: " ".join(v) if isinstance(v, list) else v for k, v in current_row.items()})
            
            # 初期化
            current_row = {"ページ": filename, "曲名": [], "読み": [], "備考": []}
            current_row_y = y_min

        # X座標に基づいて「右から左」の順に列を判定
        # 右側にあるものほど先に評価される
        if x_min > x_border_right:
            current_row["備考"].append(text)
        elif x_min > x_border_left:
            current_row["読み"].append(text)
        else:
            current_row["曲名"].append(text)

    # 最後の行を処理
    if any(current_row[k] for k in ["曲名", "読み", "備考"]):
        rows.append({k: " ".join(v) if isinstance(v, list) else v for k, v in current_row.items()})
    
    return rows

def natural_sort_key(s):
    """ファイル名を数字の順(1, 2, 10...)でソートするためのキー"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# --- メイン設定 ---

# 1. 入力フォルダの指定
input_dir = r"C:\Users\shinta\ndlocr_temp\ndlocr_cli\output\output_20260223110516\img"

# 2. ファイル一覧の取得と並べ替え
json_files = sorted(glob.glob(os.path.join(input_dir, "*.json")), key=natural_sort_key)

all_data_rows = []
print(f"合計 {len(json_files)} ファイルの処理を開始します...")

for file_path in json_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            content = json.load(f)
            # JSONが[[...]]のようにネストされている場合への対応
            flat_data = content[0] if isinstance(content[0][0], list) else content
            
            filename = os.path.basename(file_path)
            all_data_rows.extend(ocr_to_rows(flat_data, filename))
        except Exception as e:
            print(f"スキップ: {file_path} (エラー: {e})")

# 3. CSVへの出力
df = pd.DataFrame(all_data_rows)
df = df[["ページ", "曲名", "読み", "備考"]] # 列の並び順を固定

output_csv = "NDLOCR_Final_Result.csv"
df.to_csv(output_csv, index=False, encoding="utf_8_sig")

print(f"処理が完了しました。ファイル名: {output_csv}")