# -*- coding: utf-8 -*-
"""
Japan Search SPARQL自動取得 ＆ 深層メタデータ構築モジュール (BuildMetadata.py 準拠)
"""

import os
import sys
import time
import json
import requests
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
    クエリ生成関数(limit, last_uri)を呼び出し、Japan SearchからURIを自動バッチ取得します。
    エラー発生時は動的にLIMITを縮小して負荷を下げ、自動リトライします。
    """
    collected_uris = []
    last_uri = None
    current_limit = limit
    retry_count = 0

    print(f"\n--- [開始] {pattern_name} ---")

    while True:
        query = query_func(current_limit, last_uri)
        params = {'query': query, 'format': 'json'}

        try:
            cursor_info = str(last_uri)[-20:] if last_uri else 'START'
            print(f"[{pattern_name}] Fetching (limit={current_limit}) after: ...{cursor_info} ...", end=" ")
            start_time = time.time()

            response = requests.get(ENDPOINT, params=params, timeout=60)

            if response.status_code != 200:
                print(f"\n[Error] Status Code: {response.status_code}")
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    print(f"!!! リトライ回数上限 ({MAX_RETRIES}) に達しました。このクエリを終了します。")
                    break

                current_limit = max(50, current_limit // 2)
                wait_time = 5 * retry_count
                print(f"-> 待機 {wait_time}秒... LIMITを {current_limit} に縮小して再試行します。")
                time.sleep(wait_time)
                continue

            data = response.json()
            bindings = data['results']['bindings']

            if retry_count > 0:
                print(" [復帰成功] ", end="")
                retry_count = 0
                current_limit = limit

            if not bindings:
                print("Done (No more results).")
                break

            current_uris = [b['s']['value'] for b in bindings if 's' in b]
            collected_uris.extend(current_uris)

            elapsed = time.time() - start_time
            print(f"Got {len(current_uris)} items. (Subtotal: {len(collected_uris)}) [{elapsed:.2f}s]")

            if progress_callback:
                progress_callback(pattern_name, len(collected_uris))

            last_uri = current_uris[-1]

            if len(current_uris) < current_limit:
                print(f"Last batch for {pattern_name}.")
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"\n[Exception] {e}")
            retry_count += 1
            if retry_count > MAX_RETRIES:
                print(f"!!! 例外によるリトライ上限 ({MAX_RETRIES}) に達しました。")
                break
            current_limit = max(50, current_limit // 2)
            wait_time = 5 * retry_count
            print(f"-> 待機 {wait_time}秒... LIMITを {current_limit} に縮小して再試行します。")
            time.sleep(wait_time)

    return collected_uris


def fetch_deep_graph(uris: list) -> list:
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得 (BuildMetadata.py 準拠)
    """
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
    
    params = {'query': query, 'format': 'json'}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(ENDPOINT, params=params, timeout=60)
            if response.status_code == 200:
                return response.json()['results']['bindings']
            else:
                print(f"[Warning fetch_deep_graph] Attempt {attempt}/{MAX_RETRIES} Status Code: {response.status_code}")
        except Exception as e:
            print(f"[Error in fetch_deep_graph attempt {attempt}/{MAX_RETRIES}]: {e}")
        time.sleep(2 * attempt)
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

    with open(output_jsonl_path, 'w', encoding='utf-8') as out_f:
        for i in range(0, total_count, batch_size):
            chunk_uris = unique_uris[i:i + batch_size]
            bindings = fetch_deep_graph(chunk_uris)
            items = parse_dynamic_graph(bindings, chunk_uris)

            for item in items:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                processed_count += 1

            print(f"進捗: {processed_count} / {total_count} 件 処理完了")
            if progress_callback:
                progress_callback(processed_count, total_count)

            time.sleep(0.5)

    return processed_count


if __name__ == "__main__":
    print("BuildMetadata.py 準拠の深層メタデータモジュールがロードされました。")
