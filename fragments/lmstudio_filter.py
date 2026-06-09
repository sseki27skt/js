import json
from openai import OpenAI
from tqdm import tqdm

# =================設定=================
# 入力ファイル（5167件のデータ）
INPUT_JSONL = "fragments/target_for_llm.jsonl"

# 出力ファイル（判定結果のみの軽量ファイル）
OUTPUT_JUDGMENT = "fragments/llm_judgments.jsonl"

# テストモード（最初は20件で動作確認を推奨）
TEST_LIMIT = 4036
# ======================================

def get_id(data):
    """データからID（識別子）を取得する関数"""
    # 一般的なIDフィールド名を探す
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    # 見つからない場合はNone
    return None

def check_is_score(client, title, label, description):
    """LM Studioに判定させる"""
    
    system_prompt = "あなたは日本の古典籍と書誌情報の専門家です。JSON形式でのみ回答してください。"
    
    user_prompt = f"""
以下の書誌データは日本古典籍に関する大規模データベースの一部です。この資料が演奏のために記された「楽譜（Musical Score）」であるか判定してください。多くの資料に「譜」という語が含まれていますが、「譜」という語は多義的であり「系統立てて順序よく書き並べた記録。」
という意味で用いられる場合もあることに留意してください。

【判定基準】
- YES (true): メタデータの記述から判断して楽譜であることが確実なもの。
- NO (false): メタデータの記述から判断して確実に楽譜ではないもの。
- UNKNOWN (null): メタデータの記述から判断できないもの。

【対象データ】
タイトル: {title}
ラベル: {label}
詳細/注記: {description}

【出力形式】
以下のJSONキーのみを含むオブジェクトを出力してください。
{{
  "is_score": true または false または null,
  "reason": "判断した理由(メタデータのどこに依拠して判断をしたかを簡潔に説明してください)"
}}
"""

    try:
        response = client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content
        
        # JSON抽出処理
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                return {"is_score": None, "reason": "JSON Parse Error"}
    
    except Exception as e:
        return {"is_score": None, "reason": f"API Error: {str(e)}"}

def main():
    # LM Studio接続
    client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

    # 全行数カウント
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)

    if TEST_LIMIT:
        total_lines = min(total_lines, TEST_LIMIT)
        print(f"★テストモード: 最初の {TEST_LIMIT} 件のみ処理します")

    print("判定開始...")

    with open(INPUT_JSONL, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_JUDGMENT, 'w', encoding='utf-8') as fout:
        
        for i, line in enumerate(tqdm(fin, total=total_lines)):
            if TEST_LIMIT and i >= TEST_LIMIT:
                break
            
            try:
                data = json.loads(line)
                
                # IDと表示用タイトルの取得
                item_id = get_id(data)
                
                # タイトルの優先順位
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title_text = str(label) if label else (str(name) if name else "No Title")
                
                description = data.get('schema:description', '') or data.get('description', '')

                # IDがないデータはスキップ（紐付けできないため）
                if not item_id:
                    continue

                # LLM判定
                judgment = check_is_score(client, title_text, label, description)
                
                # 保存用レコードの作成（必要な項目のみ）
                record = {
                    "id": item_id,
                    "label": title_text,
                    "judgment": judgment.get("is_score"),  # true/false/null
                    "reason": judgment.get("reason", "")
                }
                
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                
            except json.JSONDecodeError:
                continue

    print(f"\n完了しました: {OUTPUT_JUDGMENT}")
    print("出力フォーマット: {id, label, judgment(true/false/null), reason}")

if __name__ == "__main__":
    main()