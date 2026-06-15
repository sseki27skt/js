# -*- coding: utf-8 -*-
import json
import os
import time
import requests
import urllib.parse
from bs4 import BeautifulSoup
from openai import OpenAI

def get_id(data):
    """データからID（識別子）を取得する関数"""
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

def check_is_score(client, title, label, description, model_name, search_info=None):
    """LM Studioやその他OpenAI互換APIに判定させる"""
    # システムプロンプトで思考の抑制とJSON出力を強制
    system_prompt = (
        "あなたは東アジア地域の古典籍資料を専門とする研究者であり、特に日本の伝統芸能に精通しています。\n"
        "【重要】思考プロセス（Thinking）は最小限に留め、速やかに最終判定をJSON形式でのみ出力してください。"
        "回答の前後に追加の説明テキストやMarkdownのコードブロック（```json）は絶対に出力しないでください。"
    )
    
    if search_info:
        web_info_section = f"""
【Web検索による補足情報】
{search_info}

※上記Web検索結果に「楽譜」「演奏用の譜」「歌唱用の謡本」である具体的な記述や説明が見つかった場合、それを最も重要な判定根拠として YES (true) と判定してください。
"""
        evidence_desc = "Web検索結果やメタデータのどこに依拠して判断をしたかを簡潔に説明してください"
    else:
        web_info_section = ""
        evidence_desc = "メタデータのどこに依拠して判断をしたかを簡潔に説明してください"

    user_prompt = f"""
以下の書誌データは日本古典籍に関する大規模データベースの一部です。この資料が演奏のために記された「楽譜（Musical Score）」であるか判定してください。

【判定基準】
- YES (true): メタデータやWeb検索結果から判断して楽譜（謡本、三味線譜、箏譜、雅楽譜など演奏、もしくは歌唱のための楽譜）であることが確実なもの。
- NO (false): メタデータやWeb検索結果から判断して楽譜ではないもの（系譜、年譜、図鑑、画譜、日誌、歴史書など）。
- UNKNOWN (null): メタデータおよびWeb検索結果からでも、演奏用の楽譜であるか判断できないもの。

【典型的な判定例】
- YES (true) とすべき例:
  * タイトル: 「声曲類纂」 / 詳細: 「芸能・音楽。歌唱のための楽曲集」 -> 「声曲」は歌唱用の楽曲を指すため楽譜（楽曲集）とみなす。
  * タイトル: 「三味線独稽古」 -> 演奏・稽古用の譜面。
  * タイトル: 「新撰謡本」 -> 歌唱用の譜（謡本）。
- NO (false) とすべき例:
  * タイトル: 「徳川家譜」 -> 歴史や系図（系譜）のため楽譜ではない。
  * タイトル: 「本草図譜」 -> 動植物の図鑑（画譜）のため楽譜ではない。
  * タイトル: 「葵氏艶譜」 -> 浮世絵・絵画集（画譜）のため楽譜ではない。
  * タイトル: 「阿淡御両国御譜録」 -> 郷土史料・歴史書（譜録）のため楽譜ではない。

【対象データ】
タイトル: {title}
ラベル: {label}
詳細/注記: {description}
{web_info_section}
【出力形式】
必ず以下のキーのみを持つJSONを出力してください。
{{
  "is_score": true または false または null,
  "reason": "判断した理由({evidence_desc})"
}}
"""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content
        
        # JSON抽出
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

def run_llm_judgment_generator(input_jsonl, output_jsonl, base_url, api_key, model_name, use_web_search=False, test_limit=None):
    """
    LLM判定を1件ずつ実行するジェネレータ。
    UIに進捗情報をリアルタイムに返すために、(現在の件数, 総件数, 現在処理中のタイトル, 判定レコード) を yield します。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    # OpenAIクライアント初期化
    client = OpenAI(base_url=base_url, api_key=api_key)

    # 全行数カウント
    with open(input_jsonl, 'r', encoding='utf-8', errors='replace') as f:
        total_lines = sum(1 for _ in f)

    if test_limit and test_limit > 0:
        total_lines = min(total_lines, test_limit)

    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)

    # 中途半端な終了時のために毎回上書きでオープン
    with open(input_jsonl, 'r', encoding='utf-8', errors='replace') as fin, \
         open(output_jsonl, 'w', encoding='utf-8', errors='replace') as fout:
        
        for i, line in enumerate(fin):
            if test_limit and test_limit > 0 and i >= test_limit:
                break
                
            try:
                data = json.loads(line)
                item_id = get_id(data)
                
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title_text = str(label) if label else (str(name) if name else "No Title")
                description = data.get('schema:description', '') or data.get('description', '')

                if not item_id:
                    # IDなしはスキップ
                    continue

                # 現在処理中の情報をUIに報告
                yield (i + 1, total_lines, title_text, None)

                # Web検索実行
                search_info = None
                if use_web_search:
                    search_query = f"{title_text} とは"
                    search_info = search_ddg(search_query, 3)
                    time.sleep(1) # IPブロック防止およびユーザー指定によるスリープ

                # LLM判定
                judgment = check_is_score(client, title_text, label, description, model_name, search_info=search_info)
                
                record = {
                    "id": item_id,
                    "label": title_text,
                    "judgment": judgment.get("is_score"),  # true/false/null
                    "reason": judgment.get("reason", ""),
                    "web_snippets": search_info if use_web_search else None
                }
                
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                fout.flush() # ディスクに即時書き出し
                
                # 判定結果も含めてUIに再報告
                yield (i + 1, total_lines, title_text, record)
                
            except json.JSONDecodeError:
                continue

# ----------------- データマージ -----------------

def run_merge_data(original_jsonl, judgments_jsonl, output_merged_jsonl):
    """
    LLMの判定結果 (judgments_jsonl) を元のデータ (original_jsonl) にマージし、
    人間が査読するためのマージファイル (output_merged_jsonl) を生成します。
    """
    if not os.path.exists(judgments_jsonl):
        raise FileNotFoundError(f"判定結果ファイルが見つかりません: {judgments_jsonl}")
    if not os.path.exists(original_jsonl):
        raise FileNotFoundError(f"元データファイルが見つかりません: {original_jsonl}")

    # 1. 判定結果を読み込んで辞書化 (ID -> 判定データ)
    judgments = {}
    with open(judgments_jsonl, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                row = json.loads(line)
                jid = get_id(row)
                if jid:
                    judgments[jid] = row
            except json.JSONDecodeError:
                continue

    merged_count = 0
    os.makedirs(os.path.dirname(output_merged_jsonl), exist_ok=True)

    with open(original_jsonl, 'r', encoding='utf-8', errors='replace') as fin, \
         open(output_merged_jsonl, 'w', encoding='utf-8', errors='replace') as fout:
        
        for line in fin:
            try:
                original_data = json.loads(line)
                oid = get_id(original_data)
                
                # LLM判定結果が存在するものだけをマージ
                if oid and oid in judgments:
                    judg = judgments[oid]
                    
                    original_data["_inferred_metadata"] = {
                        "is_score": judg.get("judgment"), # true/false/null
                        "genre": None,                    # プレースホルダー
                        "instruments": [],                # プレースホルダー
                        
                        "_evidence": {
                            "score_reason": judg.get("reason", ""),
                            "stage": "llm_inferred_web" if judg.get("web_snippets") else "llm_inferred",
                            "retrieved_web_snippets": [judg.get("web_snippets")] if judg.get("web_snippets") else []
                        }
                    }
                    
                    fout.write(json.dumps(original_data, ensure_ascii=False) + "\n")
                    merged_count += 1
            except json.JSONDecodeError:
                continue

    return merged_count

# ----------------- バックグラウンド実行（進捗ファイル書き出し用） -----------------

def update_progress_file(progress_path, running, current, total, title, completed=False, error=None):
    try:
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump({
                "running": running,
                "current": current,
                "total": total,
                "title": title,
                "completed": completed,
                "error": error
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def run_llm_judgment_background(input_jsonl, output_jsonl, base_url, api_key, model_name, use_web_search, test_limit, progress_path, original_jsonl, output_merged_jsonl):
    """
    バックグラウンドスレッドでLLM判定を実行し、進捗をJSONファイルに記録します。
    """
    try:
        # 初期状態書き込み
        update_progress_file(progress_path, running=True, current=0, total=1, title="準備中...", completed=False)
        
        generator = run_llm_judgment_generator(
            input_jsonl=input_jsonl,
            output_jsonl=output_jsonl,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            use_web_search=use_web_search,
            test_limit=test_limit
        )
        
        total_count = 1
        # 1件ずつ処理
        for current, total, title, record in generator:
            total_count = total
            if record is None:
                status_title = f"【判定中】 {title}"
            else:
                judge_str = "楽譜" if record.get("judgment") is True else "ノイズ" if record.get("judgment") is False else "不明"
                status_title = f"【完了】 {title} (判定: {judge_str})"
            update_progress_file(progress_path, running=True, current=current, total=total, title=status_title, completed=False)
            
        # 判定が終わったらマージ処理を実行
        update_progress_file(progress_path, running=True, current=total_count, total=total_count, title="データをマージ中...", completed=False)
        m_cnt = run_merge_data(
            original_jsonl=original_jsonl,
            judgments_jsonl=output_jsonl,
            output_merged_jsonl=output_merged_jsonl
        )
        
        # 完了状態の書き込み
        update_progress_file(progress_path, running=False, current=total_count, total=total_count, title=f"完了 (マージ件数: {m_cnt}件)", completed=True)
        
    except Exception as e:
        update_progress_file(progress_path, running=False, current=0, total=1, title="エラー発生", completed=False, error=str(e))

