# -*- coding: utf-8 -*-
"""
Japan Search SPARQL自動取得 ＆ 深層メタデータ構築モジュール (BuildMetadata.py 準拠)
"""

import os
import sys
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
from collections import defaultdict

ENDPOINT = "https://jpsearch.go.jp/rdf/sparql/"
DEFAULT_LIMIT = 500
MAX_RETRIES = 5

PREFIX_MAP = {
    "http://schema.org/": "schema:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://purl.org/dc/terms/": "dct:",
    "https://jpsearch.go.jp/term/property#": "jps:",
    "https://jpsearch.go.jp/term/property/": "jps:",
    "http://www.w3.org/2002/07/owl#": "owl:",
    "http://www.w3.org/2004/02/skos/core#": "skos:"
}


def get_robust_session() -> requests.Session:
    """
    HTTPS 443 接続を効率的に使い回し (Keep-Alive)、接続切断・タイムアウトに強いセッションを生成
    """
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def shorten_uri(uri: str) -> str:
    """
    長いURIをPrefix付きの短い文字列に変換する
    例: http://schema.org/name -> schema:name
    """
    for prefix, short in PREFIX_MAP.items():
        if uri.startswith(prefix):
            return uri.replace(prefix, short)
    return uri


def fetch_uris_with_query_func(query_func, pattern_name="Custom Query", limit=DEFAULT_LIMIT, progress_callback=None) -> list:
    """
    クエリ生成関数(limit)を呼び出し、Japan SearchからURIを一括高速取得します。
    Keep-Alive対応セッションにより、Port 443の接続エラーを回避します。
    """
    collected_uris = []
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    max_query_retries = 2
    session = get_robust_session()
    
    print(f"\n--- [開始] {pattern_name} ---")

    query = query_func(limit, None)
    data = {'query': query, 'format': 'json'}

    for attempt in range(1, max_query_retries + 1):
        try:
            print(f"[{pattern_name}] Fetching (limit={limit}) ...", end=" ")
            start_time = time.time()

            response = session.post(ENDPOINT, data=data, headers=headers, timeout=25)

            if response.status_code != 200:
                print(f"\n[Error] Status Code: {response.status_code}")
                time.sleep(2)
                continue

            resp_data = response.json()
            bindings = resp_data.get('results', {}).get('bindings', [])

            current_uris = [b['s']['value'] for b in bindings if 's' in b]
            collected_uris.extend(current_uris)

            elapsed = time.time() - start_time
            print(f"Got {len(current_uris)} items. [{elapsed:.2f}s]")

            if progress_callback:
                progress_callback(pattern_name, len(collected_uris))
            
            break

        except Exception as e:
            print(f"\n[Timeout / Exception attempt {attempt}/{max_query_retries}]: {e}")
            if attempt < max_query_retries:
                time.sleep(2)
            else:
                print(f"[{pattern_name}] 応答遅延のためスキップし、他のクエリの収集結果で処理を継続します。")

    return collected_uris


def fetch_deep_graph(uris: list, session: requests.Session = None) -> list:
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得 (BuildMetadata.py 準拠)
    """
    if not uris:
        return []
    
    if session is None:
        session = get_robust_session()

    uris_str = " ".join([f"<{u}>" for u in uris])
    
    query = f"""
    PREFIX schema: <http://schema.org/>
    PREFIX jps: <https://jpsearch.go.jp/term/property/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    CONSTRUCT {{
        ?s ?p ?o .
        ?node ?p2 ?o2 .
        ?subnode ?p3 ?o3 .
    }}
    WHERE {{
        VALUES ?s {{ {uris_str} }}
        
        ?s ?p ?o .
        
        OPTIONAL {{
            ?s ?linkProp ?node .
            FILTER (ISBLANK(?node) || (ISURI(?node) && STRSTARTS(STR(?node), STR(?s))))
            ?node ?p2 ?o2 .
            
            OPTIONAL {{
                ?o2 ?p3 ?o3 .
                FILTER (ISBLANK(?o2) || (ISURI(?o2) && STRSTARTS(STR(?o2), STR(?s))))
            }}
        }}
    }}
    """
    
    data = {'query': query, 'format': 'json'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(ENDPOINT, data=data, headers=headers, timeout=45)
            if response.status_code == 200:
                return response.json().get('results', {}).get('bindings', [])
            else:
                print(f"[Warning fetch_deep_graph] Attempt {attempt}/{MAX_RETRIES} Status Code: {response.status_code}")
        except Exception as e:
            print(f"[Error in fetch_deep_graph attempt {attempt}/{MAX_RETRIES}]: {e}")
        time.sleep(2 * attempt)

    # 失敗時、半分のチャンクに小分けにしてフォールバック再取得
    if len(uris) > 5:
        print(f"-> チャンク分割フォールバック再試行 (全 {len(uris)} 件を半分ずつ小分け取得)")
        mid = len(uris) // 2
        res1 = fetch_deep_graph(uris[:mid], session)
        res2 = fetch_deep_graph(uris[mid:], session)
        return res1 + res2

    return []


def parse_dynamic_graph(bindings: list, target_uris: list) -> list:
    """
    取得したCONSTRUCTトリプルからツリー型ネスト構造を構築 (BuildMetadata.py 準拠)
    """
    graph = defaultdict(lambda: defaultdict(list))
    for b in bindings:
        s = b['s']['value']
        p = b['p']['value']
        o = b['o']['value']
        graph[s][p].append(o)
    
    results = []
    
    for uri in target_uris:
        if uri not in graph:
            results.append({"@id": uri, "status": "failed"})
            continue
            
        def node_to_dict(current_node, visited=None):
            if visited is None:
                visited = set()
            
            if current_node in visited:
                return {"@id": current_node, "meta": "cyclic_reference"}
            
            visited.add(current_node)
            props = graph.get(current_node, {})
            node_data = {"@id": current_node}
            
            for p_uri, objects in props.items():
                short_p = shorten_uri(p_uri)
                
                parsed_objects = []
                for obj in objects:
                    if obj in graph and (obj.startswith(uri) or obj.startswith("_:")):
                        parsed_objects.append(node_to_dict(obj, visited.copy()))
                    else:
                        parsed_objects.append(obj)
                
                if len(parsed_objects) == 1:
                    node_data[short_p] = parsed_objects[0]
                else:
                    node_data[short_p] = parsed_objects

            return node_data

        structured_data = node_to_dict(uri)
        structured_data["status"] = "success"
        results.append(structured_data)
        
    return results


def build_metadata_for_uris(uri_list: list, output_jsonl_path: str, batch_size: int = 20, progress_callback=None) -> int:
    """
    収集したURIリストに対して、Japan Search SPARQLからCONSTRUCT深層グラフメタデータを
    一括取得し、BuildMetadata.py 形式の短縮キーネストJSONLファイルとして保存します。
    """
    os.makedirs(os.path.dirname(output_jsonl_path), exist_ok=True)
    
    unique_uris = sorted(list(set(uri_list)))
    total_count = len(unique_uris)
    processed_count = 0

    print(f"\n--- [深層メタデータ一括構築開始 (BuildMetadata.py準拠)] 全 {total_count} 件 ---")
    session = get_robust_session()

    with open(output_jsonl_path, 'w', encoding='utf-8') as out_f:
        for i in range(0, total_count, batch_size):
            chunk_uris = unique_uris[i:i + batch_size]
            bindings = fetch_deep_graph(chunk_uris, session=session)
            items = parse_dynamic_graph(bindings, chunk_uris)

            for item in items:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                processed_count += 1

            print(f"進捗: {processed_count} / {total_count} 件 処理完了")
            if progress_callback:
                progress_callback(processed_count, total_count)

            time.sleep(1.5)

    return processed_count


if __name__ == "__main__":
    print("BuildMetadata.py 準拠の深層メタデータモジュールがロードされました。")
