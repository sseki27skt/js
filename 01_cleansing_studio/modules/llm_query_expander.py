# -*- coding: utf-8 -*-
"""
LLMアシスト型 検索キーワード拡張 & ドメイン定義生成モジュール (Gemini API / OpenAI / Local対応)
"""

import json
import os
import re
import requests

DEFAULT_LLM_URL = os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "local-model")


def expand_query_with_llm(
    theme_prompt: str, 
    provider: str = "local", 
    api_base: str = DEFAULT_LLM_URL, 
    api_key: str = "", 
    model: str = DEFAULT_MODEL
) -> dict:
    """
    ユーザーが入力したテーマから、Japan Search検索用パラメータをLLMで自動抽出・生成します。
    provider: "local" (LM Studio/Ollama), "gemini" (Google Gemini API), "openai" (OpenAI API)
    """
    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        "ユーザーが指定したテーマ・関心領域に基づき、Japan Search（日本文化資源メタデータ検索プラットフォーム）から"
        "対象資料を漏れなく・かつ効率的に収集するための検索パラメータをJSON形式で提案してください。\n\n"
        "【重要】検索キーワードは単一の長い文章ではなく、「楽譜」「譜」「音楽」「謡本」のように資料タイトルや説明文に直接含まれる個別の単語キーワードのリストとして出してください。\n\n"
        "必ず以下の純粋で有効なJSONフォーマットのみを出力してください（コメントや説明文は不要です）：\n"
        "{\n"
        '  "theme": "テーマ名",\n'
        '  "domain_definition": "資料判定用ドメイン定義文",\n'
        '  "target_type": "type:古書・古文書",\n'
        '  "ndc_codes": ["76", "014.7", "186.5", "774.7"],\n'
        '  "keywords": ["譜", "楽譜", "樂譜", "音楽", "音譜"],\n'
        '  "title_regex": "譜|楽譜|樂譜|音楽",\n'
        '  "desc_regex": "楽譜|樂譜|音楽",\n'
        '  "expected_suffixes": ["譜", "帳", "録", "本"]\n'
        "}\n"
    )

    user_prompt = f"対象テーマ: {theme_prompt}"

    # --- 1. Google Gemini API 呼び出しロジック ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return _build_fallback_result(theme_prompt, "Gemini APIキーが設定されていません。")

        target_model = model if model and model != "local-model" else "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return parsed
            else:
                return _build_fallback_result(theme_prompt, f"Gemini API エラー (Status {res.status_code}): {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"Gemini API 接続例外: {e}")

    # --- 2. Local LLM / OpenAI 互換 API 呼び出しロジック ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n思考は行わず直ちにJSONのみ出力してください。\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 4000
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=120)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return parsed
            else:
                return _build_fallback_result(theme_prompt, f"APIエラー Status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"API接続エラー: {e}")


def _build_fallback_result(theme_prompt: str, reason: str) -> dict:
    """フォールバックルールベース結果の構築"""
    print(f"[LLM Expander] フォールバック適用: {reason}")
    if "楽譜" in theme_prompt or "音楽" in theme_prompt or "譜" in theme_prompt:
        keywords = ["譜", "楽譜", "樂譜", "音楽", "音譜"]
        title_regex = "譜|音楽"
        desc_regex = "楽譜|樂譜|音楽"
        ndc_codes = ["76", "014.7", "186.5", "774.7"]
    else:
        words = [w.strip() for w in re.split(r"[\s,・/／におけるについて]+", theme_prompt) if len(w.strip()) >= 2]
        keywords = words if words else [theme_prompt]
        title_regex = "|".join(keywords)
        desc_regex = title_regex
        ndc_codes = []

    return {
        "theme": theme_prompt,
        "domain_definition": f"「{theme_prompt}」に関連する文化資源・文献・資料",
        "target_type": "type:古書・古文書",
        "ndc_codes": ndc_codes,
        "keywords": keywords,
        "title_regex": title_regex,
        "desc_regex": desc_regex,
        "expected_suffixes": ["本", "録", "集", "帖", "図", "譜"],
        "is_fallback": True,
        "fallback_reason": reason
    }


def generate_sparql_queries(expansion_result: dict, limit: int = 500) -> list:
    """SPARQLクエリ一覧の生成"""
    target_type = expansion_result.get("target_type", "type:古書・古文書")
    type_clause = f"?s rdf:type {target_type} ." if target_type else ""

    ndc_codes = expansion_result.get("ndc_codes", [])
    title_regex = expansion_result.get("title_regex", "")
    desc_regex = expansion_result.get("desc_regex", "")
    
    queries = []
    
    # 1. NDC分類検索
    if ndc_codes:
        ndc_filters = []
        for code in ndc_codes:
            if "." in code or len(code) >= 4:
                ndc_filters.append(f"?ndc = <http://jla.or.jp/data/ndc#{code}>")
            else:
                ndc_filters.append(f'STRSTARTS(STR(?ndc), "http://jla.or.jp/data/ndc#{code}")')
        
        filter_expr = " || ".join(ndc_filters)
        
        def q_ndc(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX schema: <http://schema.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX type: <https://jpsearch.go.jp/term/type/>
            
            SELECT ?s WHERE {{
              {type_clause}
              ?s schema:genre ?ndc .
              FILTER ({filter_expr})
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("1. NDC分類検索", q_ndc))

    # 2. タイトル (rdfs:label) 検索
    if title_regex:
        def q_label(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX type: <https://jpsearch.go.jp/term/type/>
            
            SELECT ?s WHERE {{
              {type_clause}
              ?s rdfs:label ?label .
              FILTER (REGEX(?label, "{title_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("2. タイトル(label)検索", q_label))

    # 3. 名称 (schema:name) 検索
    if title_regex:
        def q_name(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX schema: <http://schema.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX type: <https://jpsearch.go.jp/term/type/>
            
            SELECT ?s WHERE {{
              {type_clause}
              ?s schema:name ?name .
              FILTER (REGEX(?name, "{title_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("3. 名称(name)検索", q_name))

    # 4. 説明文 (schema:description) 検索
    if desc_regex:
        def q_desc(lim, last_uri=None):
            f_clause = f"FILTER (?s > <{last_uri}>)" if last_uri else ""
            return f"""
            PREFIX schema: <http://schema.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX type: <https://jpsearch.go.jp/term/type/>
            
            SELECT ?s WHERE {{
              {type_clause}
              ?s schema:description ?desc .
              FILTER (REGEX(?desc, "{desc_regex}", "i"))
              {f_clause}
            }}
            ORDER BY ?s
            LIMIT {lim}
            """
        queries.append(("4. 説明文(description)検索", q_desc))

    return queries
