# -*- coding: utf-8 -*-
import json
import urllib.parse
import time
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from tqdm import tqdm

# =================設定=================
# 入力ファイル
INPUT_JSONL = "fragments/target_for_llm.jsonl"

# 出力ファイル
OUTPUT_JUDGMENT = "fragments/llm_judgments.jsonl"

# テストモード（最初は10件で動作確認を推奨。全件処理する場合は None に設定）
TEST_LIMIT = 10
# ======================================

def get_id(data):
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    return None

def search_ddg(query, num_results=3):
    """DuckDuckGoから簡易検索を行い、上位のスニペットを取得する"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            items = soup.find_all('div', class_='result')
            for item in items:
                title_elem = item.find('a', class_='result__a')
                snippet_elem = item.find('a', class_='result__snippet')
                
                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    results.append(f"・{title}\n  {snippet}")
                    if len(results) >= num_results:
                        break
            
            if not results:
                for a in soup.find_all('a', class_='result__snippet'):
                    results.append(a.get_text(strip=True))
                    if len(results) >= num_results:
                        break
            
            return "\n".join(results) if results else "検索結果なし"
        else:
            return f"検索エラー (ステータスコード: {response.status_code})"
    except Exception as e:
        return f"検索エラー: {str(e)}"

def check_is_score(client, title, label, description, search_info):
    """LM Studioに判定させる (Web検索結果付き)"""
    system_prompt = "あなたは東アジア地域の古典籍資料を専門とする研究者であり、特に日本の伝統芸能に精通しています。JSON形式でのみ回答してください。"
    user_prompt = f"""
以下の書誌データは日本古典籍に関する大規模データベースの一部です。この資料が演奏のために記された「楽譜（Musical Score）」であるか判定してください。多くの資料に「譜」という語が含まれていますが、「譜」という語は多義的であり「系統立てて順序よく書き並べた記録。」（年譜、系譜、画譜、印譜など）という意味で用いられる場合もあることに留意してください。

【判定基準】
- YES (true): メタデータやWeb検索結果から判断して楽譜（謡本、三味線譜、箏譜、雅楽譜など演奏のための楽譜）であることが確実なもの。
- NO (false): メタデータやWeb検索結果から判断して楽譜ではないもの（系譜、年譜、図鑑、画譜、日誌、歴史書、あるいは歌集や歌詞のみのテキスト集など）。
- UNKNOWN (null): メタデータおよびWeb検索結果からでも、演奏用の楽譜であるか判断できないもの。

【対象データ】
タイトル: {title}
ラベル: {label}
詳細/注記: {description}

【Web検索による補足情報】
{search_info}

【出力形式】
以下のJSONキーのみを含むオブジェクトを出力してください。
{{
  "is_score": true または false または null,
  "reason": "判断した理由(Web検索結果やメタデータのどこに依拠して判断をしたかを簡潔に説明してください)"
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

    print("Web検索とLLMによる判定を開始します（全件Web検索適用版）...")

    with open(INPUT_JSONL, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_JUDGMENT, 'w', encoding='utf-8') as fout:
        
        for i, line in enumerate(tqdm(fin, total=total_lines)):
            if TEST_LIMIT and i >= TEST_LIMIT:
                break
            
            try:
                data = json.loads(line)
                
                # IDと表示用タイトルの取得
                item_id = get_id(data)
                if not item_id:
                    continue
                
                # タイトルの優先順位
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title_text = str(label) if label else (str(name) if name else "No Title")
                
                description = data.get('schema:description', '') or data.get('description', '')

                # 1. 必ずWeb検索を実行
                search_query = f"{title_text} とは"
                search_info = search_ddg(search_query, 3)
                
                # IPブロック防止のための適度なスリープ
                time.sleep(1.5)

                # 2. LLM判定
                judgment = check_is_score(client, title_text, label, description, search_info)
                
                # 保存用レコードの作成
                record = {
                    "id": item_id,
                    "label": title_text,
                    "judgment": judgment.get("is_score"),  # true/false/null
                    "reason": judgment.get("reason", ""),
                    "stage": "secondary_web" # 全件Web検索のため、検証ツール側ではすべて「Web検索判定」として扱われるように統一
                }
                
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                
            except json.JSONDecodeError:
                continue

    print(f"\n完了しました: {OUTPUT_JUDGMENT}")

if __name__ == "__main__":
    main()
