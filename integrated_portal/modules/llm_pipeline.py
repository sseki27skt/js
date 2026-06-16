# -*- coding: utf-8 -*-
import json
import os
import time
import sys
import requests
import urllib.parse
import random
from bs4 import BeautifulSoup
from openai import OpenAI
from ddgs import DDGS

# Windows / Streamlit のモジュール再ロード対策として sys に状態を逃がす
if not hasattr(sys, "_global_llm_progress"):
    sys._global_llm_progress = {
        "running": False,
        "current": 0,
        "total": 1,
        "title": "準備中...",
        "completed": False,
        "error": None,
        "stop_requested": False,
        "web_status": None
    }

def get_progress():
    return sys._global_llm_progress.copy()

def set_progress(data):
    sys._global_llm_progress.update(data)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def get_id(data):
    """データからID（識別子）を取得する関数"""
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    return None

def search_wikipedia(query):
    """Wikipedia APIから要約を取得する"""
    clean_query = query.replace(" とは", "").replace("とは", "").strip()
    url = f"https://ja.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(clean_query)}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS)
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                if page_id != "-1":
                    title = page_info.get("title")
                    extract = page_info.get("extract", "")
                    if extract:
                        return f"・Wikipedia: {title}\n  {extract[:300]}"
            return None
        return f"Wikipediaエラー (ステータスコード: {response.status_code})"
    except Exception as e:
        return f"Wikipediaエラー: {str(e)}"

def search_ddg_backend(query, num_results=5):
    """DuckDuckGoから簡易検索を行い、上位のスニペットを取得する（ddgsライブラリを使用）"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="jp-jp", max_results=num_results))
            if not results:
                return "検索結果なし"
            
            output = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                output.append(f"・{title}\n  {body}")
            return "\n".join(output)
    except Exception as e:
        return f"DuckDuckGoエラー: {str(e)}"

def search_ddg(query, num_results=3):
    """
    DuckDuckGo と Wikipedia を併用して検索結果を取得する。
    1. まず DuckDuckGo 検索を試行 (ddgsライブラリを使用)。
    2. DuckDuckGo で該当なし、あるいはエラーの場合は、Wikipedia 検索をフォールバックとして実行する。
    """
    # 1. DuckDuckGo 検索を試行
    ddg_result = search_ddg_backend(query, num_results)
    if ddg_result and not ddg_result.startswith("DuckDuckGoエラー") and ddg_result != "検索結果なし":
        return ddg_result
        
    # 2. Wikipedia 検索を試行 (フォールバック)
    wiki_result = search_wikipedia(query)
    if wiki_result and not wiki_result.startswith("Wikipediaエラー"):
        return wiki_result
        
    return ddg_result



def check_is_score(client, title, label, description, model_name, search_info=None):
    """LM Studioやその他OpenAI互換APIに判定させる"""
    # システムプロンプトで思考の抑制とJSON出力を強制
    system_prompt = (
        "あなたは東アジア地域の古典籍資料を専門とする研究者であり、特に日本の伝統芸能に精通しています。\n"
        "最終判定はJSON形式でのみ出力してください。"
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
- YES (true): メタデータやWeb検索結果から判断して楽譜（謡本、三味線譜、箏譜、雅楽譜などの演奏、もしくは義太夫の床本など歌唱のための楽譜）であることが確実なもの。
- NO (false): メタデータやWeb検索結果から判断して楽譜ではないもの（系譜、年譜、図鑑、画譜、日誌、歴史書など）。
- UNKNOWN (null): メタデータおよびWeb検索結果からでも、演奏用の楽譜であるか判断できないもの。

【典型的な判定例】
- YES (true) とすべき例:
  * タイトル: 「三味線独稽古」 -> 演奏・稽古用の譜面。
  * タイトル: 「新撰謡本」 -> 歌唱用の譜（謡本）。
  
- NO (false) とすべき例:
  * タイトル: 「声曲類纂」 -> 江戸時代の音曲に関して書かれた音楽関連書籍ではあるものの楽譜ではない。
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
            timeout=30.0  # モデルハング時のUIフリーズ防止用にタイムアウトを設定
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
    UIに進捗情報をリアルタイムに返すために、(現在の件数, 総件数, 現在処理中のタイトル, 判定レコード, Web検索ステータス) を yield します。
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
                yield (i + 1, total_lines, title_text, None, "待機中...")

                # Web検索実行
                search_info = None
                web_status = "Web検索オフ"
                if use_web_search:
                    search_query = f"{title_text} とは"
                    yield (i + 1, total_lines, title_text, None, "🔍 Web検索リクエスト中...")
                    search_info = search_ddg(search_query, 3)
                    
                    if not search_info or search_info == "検索結果なし":
                        web_status = "⚠️ 検索結果なし (Wikipedia / DuckDuckGo)"
                    elif search_info.startswith("・Wikipedia:"):
                        web_status = "📚 Wikipediaからデータ取得"
                    elif "エラー" in search_info or "status:" in search_info or "status_code:" in search_info:
                        web_status = f"❌ 検索エラー ({search_info})"
                    else:
                        web_status = "🌐 DuckDuckGoからデータ取得"
                    
                    yield (i + 1, total_lines, title_text, None, web_status)
                    time.sleep(1.5) # IPブロック防止およびユーザー指定によるスリープ

                # LLM判定
                yield (i + 1, total_lines, title_text, None, f"{web_status} ➡ 🤖 LLM判定中...")
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
                yield (i + 1, total_lines, title_text, record, web_status)
                
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

def check_stop_requested(progress_path):
    # メモリ上の中断シグナルを優先して確認
    if sys._global_llm_progress.get("stop_requested", False):
        return True
    # ファイルからのフォールバック確認
    if not os.path.exists(progress_path):
        return False
    for _ in range(5):
        try:
            with open(progress_path, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)
                return data.get("stop_requested", False)
        except (IOError, PermissionError, json.JSONDecodeError):
            time.sleep(0.05)
    return False

def update_progress_file(progress_path, running, current, total, title, completed=False, error=None, stop_requested=False, web_status=None):
    # メモリ上のグローバル進捗変数を瞬時に更新（遅延・ファイルロックなし）
    set_progress({
        "running": running,
        "current": current,
        "total": total,
        "title": title,
        "completed": completed,
        "error": error,
        "stop_requested": stop_requested,
        "web_status": web_status
    })
    
    # 物理ファイルへの書き出しも試みる
    data = {
        "running": running,
        "current": current,
        "total": total,
        "title": title,
        "completed": completed,
        "error": error,
        "stop_requested": stop_requested,
        "web_status": web_status
    }
    
    temp_path = progress_path + ".tmp"
    # 1. 一時ファイルに書き出す (メインファイルへの書き込み競合を避ける)
    for _ in range(3):
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            break
        except Exception:
            time.sleep(0.02)
            
    # 2. 一時ファイルをメインファイルに置き換える (Windows対応)
    for _ in range(3):
        try:
            if os.path.exists(progress_path):
                os.remove(progress_path)
            os.rename(temp_path, progress_path)
            break
        except Exception:
            time.sleep(0.02)

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
        stopped = False
        current_idx = 0
        
        # 1件ずつ処理
        for current, total, title, record, web_status in generator:
            total_count = total
            current_idx = current
            
            # 中断フラグが立っているかチェック
            if check_stop_requested(progress_path):
                stopped = True
                break
                
            if record is None:
                status_title = f"【判定中】 {title}"
            else:
                judge_str = "楽譜" if record.get("judgment") is True else "ノイズ" if record.get("judgment") is False else "不明"
                status_title = f"【完了】 {title} (判定: {judge_str})"
            update_progress_file(progress_path, running=True, current=current, total=total, title=status_title, completed=False, web_status=web_status)
            
        if stopped:
            # 中断された場合、そこまでの結果をマージして保存
            update_progress_file(progress_path, running=False, current=current_idx - 1, total=total_count, title="処理を中断しています（マージ中）...", completed=False, stop_requested=True)
            m_cnt = run_merge_data(
                original_jsonl=original_jsonl,
                judgments_jsonl=output_jsonl,
                output_merged_jsonl=output_merged_jsonl
            )
            update_progress_file(progress_path, running=False, current=current_idx - 1, total=total_count, title=f"ユーザーにより中断されました (判定済み {current_idx - 1} 件をマージ完了)", completed=True, stop_requested=True)
            return

        # 判定が最後まで終わったらマージ処理を実行
        update_progress_file(progress_path, running=True, current=total_count, total=total_count, title="データをマージ中...", completed=False)
        m_cnt = run_merge_data(
            original_jsonl=original_jsonl,
            judgments_jsonl=output_jsonl,
            output_merged_jsonl=output_merged_jsonl
        )
        
        # 完了状態の書き込み
        update_progress_file(progress_path, running=False, current=total_count, total=total_count, title=f"完了 (マージ件数: {m_cnt}件)", completed=True)
        
    except Exception as e:
        import traceback
        print("="*60, flush=True)
        print("【エラー】LLM判定バックグラウンドスレッドで例外が発生しました:", flush=True)
        traceback.print_exc()
        print("="*60, flush=True)
        update_progress_file(progress_path, running=False, current=0, total=1, title=f"エラー発生: {str(e)}", completed=False, error=str(e))

