# -*- coding: utf-8 -*-
"""
LLMセマンティック自動判定 (グレーゾーン分類) モジュール (Gemini API / OpenAI / Local対応)
"""

import json
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_llm_semantic_classification(
    input_jsonl_path: str,
    output_judgments_path: str,
    domain_definition: str = "日本の古典籍における楽譜・音楽資料",
    provider: str = "gemini",
    api_base: str = "http://localhost:1234/v1",
    api_key: str = "",
    model: str = "gemini-3.6-flash",
    limit: int = None,
    max_workers: int = 4,
    progress_callback=None
) -> tuple:
    """
    データセット内の資料に対し、LLMがタイトル・説明文・注記をセマンティック解析して
    「目的資料として適合するか」を判定理由(reason)付きで判定します。
    """
    if not os.path.exists(input_jsonl_path):
        return 0, 0, 0

    os.makedirs(os.path.dirname(output_judgments_path), exist_ok=True)

    items = []
    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.strip():
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue

    if limit:
        items = items[:limit]

    total_items = len(items)
    accepted_count = 0
    rejected_count = 0
    unknown_count = 0

    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        f"【対象ドメイン定義】: {domain_definition}\n\n"
        "提示された書誌データが、上記の対象ドメイン資料として適合するか判定し、必ず純粋なJSONフォーマットのみを出力してください。\n"
        "【出力形式】:\n"
        "{\n"
        '  "is_target": true または false または null,\n'
        '  "reason": "メタデータのどこに依拠して判断したかの簡潔な理由"\n'
        "}\n"
    )

    # ローカルLLMの場合はシングルスレッドで負荷を抑える
    eff_workers = 1 if provider.lower() in ["local", "lmstudio"] else max(1, max_workers)

    def process_item(idx_item):
        idx, item = idx_item
        item_id = item.get("@id", item.get("id", f"item_{idx}"))
        label = item.get("rdfs:label", item.get("schema:name", "No Title"))
        title = label[0] if isinstance(label, list) and label else str(label)
        
        desc_val = item.get("schema:description", "")
        desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)

        user_prompt = (
            f"タイトル: {title}\n"
            f"詳細/説明文: {desc[:400] if desc else '記述なし'}\n"
            f"分類/ジャンル: {item.get('schema:genre', 'なし')}\n"
        )

        judgment = _classify_single_item(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            api_base=api_base,
            api_key=api_key,
            model=model
        )

        is_target = judgment.get("is_target")
        reason = judgment.get("reason", "判定完了")

        res_obj = {
            "index": idx,
            "id": item_id,
            "title": title,
            "is_target": is_target,
            "reason": reason,
            "raw_item": item
        }
        return res_obj

    results_dict = {}
    completed_counter = 0

    if eff_workers > 1:
        with ThreadPoolExecutor(max_workers=eff_workers) as executor:
            future_to_idx = {executor.submit(process_item, (i, item)): i for i, item in enumerate(items)}
            for future in as_completed(future_to_idx):
                res_obj = future.result()
                results_dict[res_obj["index"]] = res_obj
                completed_counter += 1

                if res_obj["is_target"] is True:
                    accepted_count += 1
                elif res_obj["is_target"] is False:
                    rejected_count += 1
                else:
                    unknown_count += 1

                if progress_callback:
                    progress_callback(completed_counter, total_items, res_obj["title"], res_obj["is_target"], res_obj["reason"])
    else:
        for idx, item in enumerate(items):
            res_obj = process_item((idx, item))
            results_dict[idx] = res_obj
            completed_counter += 1

            if res_obj["is_target"] is True:
                accepted_count += 1
            elif res_obj["is_target"] is False:
                rejected_count += 1
            else:
                unknown_count += 1

            if progress_callback:
                progress_callback(completed_counter, total_items, res_obj["title"], res_obj["is_target"], res_obj["reason"])

    # 元の順序に揃えてリスト化
    results = [results_dict[i] for i in range(len(items)) if i in results_dict]

    # 結果をJSONLへ保存
    with open(output_judgments_path, 'w', encoding='utf-8') as f:
        for r in results:
            clean_r = {k: v for k, v in r.items() if k != "index"}
            f.write(json.dumps(clean_r, ensure_ascii=False) + "\n")

    return accepted_count, rejected_count, unknown_count


def _classify_single_item(system_prompt: str, user_prompt: str, provider: str, api_base: str, api_key: str, model: str, max_retries: int = 3) -> dict:
    """単一アイテムのLLM判定リクエスト (429自動リトライ付き)"""
    # --- 1. Google Gemini API ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return {"is_target": None, "reason": "Gemini APIキー未設定"}

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json"
            }
        }

        for attempt in range(max_retries):
            try:
                res = requests.post(url, json=payload, timeout=25)
                if res.status_code == 200:
                    text_content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return _parse_json_response(text_content)
                elif res.status_code == 429:
                    wait_sec = 2 ** (attempt + 1)
                    time.sleep(wait_sec)
                    continue
                else:
                    return {"is_target": None, "reason": f"Gemini API Status Code: {res.status_code}"}
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"is_target": None, "reason": f"Gemini API Error: {e}"}
                time.sleep(1)

        return {"is_target": None, "reason": "Gemini API Rate limit (429)"}

    # --- 2. Local LLM / OpenAI ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 500
        }

        for attempt in range(max_retries):
            try:
                url = f"{api_base.rstrip('/')}/chat/completions"
                res = requests.post(url, json=payload, headers=req_headers, timeout=30)
                if res.status_code == 200:
                    choice_msg = res.json()["choices"][0]["message"]
                    content = choice_msg.get("content") or choice_msg.get("reasoning_content", "")
                    return _parse_json_response(content)
                elif res.status_code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                else:
                    return {"is_target": None, "reason": f"API Status Code: {res.status_code}"}
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"is_target": None, "reason": f"API Error: {e}"}
                time.sleep(1)

    return {"is_target": None, "reason": "判定不能"}


def _parse_json_response(raw_text: str) -> dict:
    """Markdown装飾（```json ... ```）を除去して構造化JSON辞書を抽出"""
    if not raw_text:
        return {"is_target": None, "reason": "レスポンスが空です"}
    cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    return {"is_target": None, "reason": f"JSON解析失敗: {raw_text[:60]}"}

