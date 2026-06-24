# -*- coding: utf-8 -*-
import json
import os
import time
import sys
from openai import OpenAI

# Windows / Streamlit のモジュール再ロード対策として sys に状態を逃がす
if not hasattr(sys, "_global_metadata_progress"):
    sys._global_metadata_progress = {
        "running": False,
        "current": 0,
        "total": 1,
        "title": "準備中...",
        "completed": False,
        "error": None,
        "stop_requested": False
    }

def get_progress():
    return sys._global_metadata_progress.copy()

def set_progress(data):
    sys._global_metadata_progress.update(data)

def get_id(data):
    for key in ['id', '@id', 'uri', 'url']:
        if key in data:
            return data[key]
    return None

# 定義データ
GENRES = {
    "雅楽": ["唐楽", "高麗楽", "国風歌舞", "催馬楽", "朗詠"],
    "能楽/謡曲": ["能", "狂言", "謡曲"],
    "三味線音楽": ["地歌", "長唄", "義太夫節", "常磐津節", "清元節", "新内節", "端唄/俗曲"],
    "琵琶楽": ["平曲（平家琵琶）", "薩摩琵琶", "筑前琵琶"],
    "尺八楽": ["本曲", "外曲（琴古流・都山流等）"],
    "声明/仏教音楽": [],
    "近現代邦楽/洋楽": [],
    "その他/不明": []
}

INSTRUMENTS = ["唄/声", "箏/琴", "三味線", "尺八", "琵琶", "笙", "篳篥", "龍笛/高麗笛/神楽笛", "篠笛/能管", "鼓/太鼓", "その他"]

def estimate_music_metadata(client, title, label, description, model_name, web_snippets=None):
    """LM StudioやOpenAI互換APIに音楽メタデータを推定させる"""
    system_prompt = (
        "あなたは日本伝統音楽および古典籍資料を専門とする研究者です。\n"
        "提供された資料情報（タイトル、ラベル、説明、Web検索情報）を読み込み、資料の「大ジャンル」「サブジャンル」「使用楽器」を適切に判定してください。\n"
        "回答はJSON形式でのみ出力してください。追加の説明テキストやMarkdownのコードブロック（```json）は絶対に出力しないでください。"
    )

    genres_desc = "\n".join([f"- {g}: {', '.join(subs) if subs else 'なし'}" for g, subs in GENRES.items()])
    instruments_desc = ", ".join(INSTRUMENTS)

    user_prompt = f"""
以下の日本古典籍の楽譜資料に関する情報を分析し、「大ジャンル」「サブジャンル」「使用楽器（複数選択可）」を推定してください。

【分類の定義】
■ 大ジャンルと対応するサブジャンル:
{genres_desc}

■ 使用楽器 (以下の候補から選定してください):
{instruments_desc}

【対象資料データ】
タイトル: {title}
ラベル: {label}
説明/詳細: {description}
Web検索補足情報: {web_snippets if web_snippets else "なし"}

【出力形式】
必ず以下のキーのみを持つJSONを出力してください。楽器（instruments）は配列形式で出力し、該当するものがない場合は空配列、不明な場合は「その他」にしてください。
{{
  "genre": "上記の大ジャンルから1つ選択。該当がない場合は「その他/不明」",
  "subgenre": "大ジャンルに対応するサブジャンルから1つ選択。なければ null",
  "instruments": ["選択した楽器の配列"],
  "reason": "推定した根拠（タイトル中の語彙や説明文からの直接的・間接的証拠を簡潔に説明）"
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
            timeout=30.0
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
                return {
                    "genre": "その他/不明",
                    "subgenre": None,
                    "instruments": [],
                    "reason": f"JSON Parse Error: Output was: {content[:100]}"
                }
    except Exception as e:
        return {
            "genre": "その他/不明",
            "subgenre": None,
            "instruments": [],
            "reason": f"API Error: {str(e)}"
        }

def run_metadata_enrichment_generator(input_jsonl, output_jsonl, base_url, api_key, model_name, test_limit=None):
    """
    メタデータ付与を1件ずつ実行するジェネレータ。
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_jsonl}")

    client = OpenAI(base_url=base_url, api_key=api_key)

    # 全行数カウント (すでにis_scoreがTrueと判定された楽譜レコードのみを対象にする)
    target_lines = []
    with open(input_jsonl, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                inf_meta = data.get("_inferred_metadata", {})
                # is_scoreがTrueのものだけを対象とする
                if inf_meta.get("is_score") is True:
                    target_lines.append(data)
            except Exception:
                continue

    total_lines = len(target_lines)
    if test_limit and test_limit > 0:
        total_lines = min(total_lines, test_limit)

    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)

    # 一時保存用の配列
    enriched_results = {}

    for i, data in enumerate(target_lines):
        if test_limit and test_limit > 0 and i >= test_limit:
            break
            
        try:
            item_id = get_id(data)
            label = data.get('rdfs:label')
            name = data.get('schema:name')
            title_text = str(label) if label else (str(name) if name else "No Title")
            description = data.get('schema:description', '') or data.get('description', '')

            inf_meta = data.get("_inferred_metadata", {})
            evidence = inf_meta.get("_evidence", {})
            web_snippets = evidence.get("retrieved_web_snippets", [])
            web_text = web_snippets[0] if web_snippets else None

            # 現在処理中の情報をUIに報告
            yield (i + 1, total_lines, title_text, None)

            # LLM推定
            estimation = estimate_music_metadata(
                client=client,
                title=title_text,
                label=label,
                description=description,
                model_name=model_name,
                web_snippets=web_text
            )

            # 推定結果をレコードに格納
            enriched_record = {
                "id": item_id,
                "label": title_text,
                "genre": estimation.get("genre", "その他/不明"),
                "subgenre": estimation.get("subgenre"),
                "instruments": estimation.get("instruments", []),
                "reason": estimation.get("reason", "")
            }

            enriched_results[item_id] = enriched_record
            
            # 判定結果も含めてUIに再報告
            yield (i + 1, total_lines, title_text, enriched_record)

        except Exception as e:
            print(f"[Enricher] エラー (インデックス {i}): {e}", flush=True)
            continue

    # 結果を物理ファイル（JSONL）に保存
    with open(output_jsonl, 'w', encoding='utf-8') as fout:
        for item_id, record in enriched_results.items():
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

def check_stop_requested(progress_path):
    if sys._global_metadata_progress.get("stop_requested", False):
        return True
    if not os.path.exists(progress_path):
        return False
    try:
        with open(progress_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("stop_requested", False)
    except:
        return False

def update_progress_file(progress_path, running, current, total, title, completed=False, error=None, stop_requested=False):
    sys._global_metadata_progress.update({
        "running": running,
        "current": current,
        "total": total,
        "title": title,
        "completed": completed,
        "error": error,
        "stop_requested": stop_requested
    })
    
    data = {
        "running": running,
        "current": current,
        "total": total,
        "title": title,
        "completed": completed,
        "error": error,
        "stop_requested": stop_requested
    }
    
    temp_path = progress_path + ".tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(progress_path):
            os.remove(progress_path)
        os.rename(temp_path, progress_path)
    except:
        pass

def run_metadata_enrichment_background(input_jsonl, output_jsonl, base_url, api_key, model_name, test_limit, progress_path):
    """
    バックグラウンドスレッドでメタデータ自動推定を実行する。
    """
    try:
        update_progress_file(progress_path, running=True, current=0, total=1, title="準備中...", completed=False)
        
        generator = run_metadata_enrichment_generator(
            input_jsonl=input_jsonl,
            output_jsonl=output_jsonl,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            test_limit=test_limit
        )
        
        total_count = 1
        stopped = False
        current_idx = 0
        
        for current, total, title, record in generator:
            total_count = total
            current_idx = current
            
            if check_stop_requested(progress_path):
                stopped = True
                break
                
            if record is None:
                status_title = f"【推定中】 {title}"
            else:
                status_title = f"【推定完了】 {title} ({record.get('genre')} / {', '.join(record.get('instruments', []))})"
            update_progress_file(progress_path, running=True, current=current, total=total, title=status_title, completed=False)
            
        if stopped:
            update_progress_file(progress_path, running=False, current=current_idx - 1, total=total_count, title="推定処理がユーザーにより中断されました。", completed=True, stop_requested=True)
            return

        update_progress_file(progress_path, running=False, current=total_count, total=total_count, title="音楽的メタデータの自動推定が完了しました。", completed=True)
        
    except Exception as e:
        import traceback
        print("【エラー】メタデータ推定バックグラウンド処理で例外が発生しました:", flush=True)
        traceback.print_exc()
        update_progress_file(progress_path, running=False, current=0, total=1, title=f"エラー発生: {str(e)}", completed=False, error=str(e))

def merge_enriched_metadata(original_merged_jsonl, enriched_jsonl, output_merged_jsonl):
    """
    自動推定された音楽的メタデータを査読用データにマージする
    """
    if not os.path.exists(enriched_jsonl):
        return 0
        
    # 推定データを読み込む
    enriched_data = {}
    with open(enriched_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                eid = row.get("id")
                if eid:
                    enriched_data[eid] = row
            except:
                continue
                
    merged_count = 0
    temp_output = output_merged_jsonl + ".tmp"
    
    with open(original_merged_jsonl, 'r', encoding='utf-8', errors='replace') as fin, \
         open(temp_output, 'w', encoding='utf-8') as fout:
         
        for line in fin:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                oid = get_id(data)
                
                if oid and oid in enriched_data:
                    enrich = enriched_data[oid]
                    if "_inferred_metadata" not in data:
                        data["_inferred_metadata"] = {}
                        
                    data["_inferred_metadata"].update({
                        "genre": enrich.get("genre", "その他/不明"),
                        "subgenre": enrich.get("subgenre"),
                        "instruments": enrich.get("instruments", []),
                        "_music_reason": enrich.get("reason", "")
                    })
                    merged_count += 1
                
                fout.write(json.dumps(data, ensure_ascii=False) + "\n")
            except Exception as e:
                # 失敗時はそのまま書く
                fout.write(line)
                
    if os.path.exists(output_merged_jsonl):
        os.remove(output_merged_jsonl)
    os.rename(temp_output, output_merged_jsonl)
    return merged_count
