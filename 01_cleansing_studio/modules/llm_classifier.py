# -*- coding: utf-8 -*-
"""
LLMセマンティック自動判定 (グレーゾーン分類) モジュール (Gemini API / OpenAI / Local対応)
"""

import json
import os
import re
import requests


def run_llm_semantic_classification(
    input_jsonl_path: str,
    output_judgments_path: str,
    domain_definition: str = "日本の古典籍における楽譜・音楽資料",
    provider: str = "gemini",
    api_base: str = "http://localhost:1234/v1",
    api_key: str = "",
    model: str = "gemini-3.6-flash",
    limit: int = None,
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

    results = []

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

    for idx, item in enumerate(items):
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

        if is_target is True:
            accepted_count += 1
        elif is_target is False:
            rejected_count += 1
        else:
            unknown_count += 1

        results.append({
            "id": item_id,
            "title": title,
            "is_target": is_target,
            "reason": reason,
            "raw_item": item
        })

        if progress_callback:
            progress_callback(idx + 1, total_items, title, is_target, reason)

    # 結果をJSONLへ保存
    with open(output_judgments_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return accepted_count, rejected_count, unknown_count


def _classify_single_item(system_prompt: str, user_prompt: str, provider: str, api_base: str, api_key: str, model: str) -> dict:
    """単一アイテムのLLM判定リクエスト"""
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

        try:
            res = requests.post(url, json=payload, timeout=25)
            if res.status_code == 200:
                text_content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_content.strip())
        except Exception as e:
            return {"is_target": None, "reason": f"Gemini API Error: {e}"}

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

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=30)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or choice_msg.get("reasoning_content", "")
                
                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
                json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)
                return json.loads(cleaned)
        except Exception as e:
            return {"is_target": None, "reason": f"API Error: {e}"}

    return {"is_target": None, "reason": "判定不能"}
