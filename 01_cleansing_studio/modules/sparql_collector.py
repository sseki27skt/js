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


def fetch_uris_with_query_func(
    query_func, 
    pattern_name="Custom Query", 
    limit=500, 
    unlimited: bool = True, 
    progress_callback=None, 
    timeout_sec=45, 
    max_query_retries=3
) -> tuple:
    """
    クエリ生成関数(limit, offset)を呼び出し、Japan SearchからURIを自動ページネーション取得します。
    unlimited=True の場合、該当する全データが尽きるまで何千〜何万件でも全件自動収集します。
    504エラー等が発生した場合は自動的にLIMITを縮小して自律回復します。
    """
    collected_uris = []
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    session = get_robust_session()
    base_batch_size = limit if limit and limit > 0 else 500
    current_limit = base_batch_size
    target_limit = limit if (not unlimited and limit and limit > 0) else None

    target_str = f"目標: {target_limit}件" if target_limit else "全件網羅 (上限なし)"
    print(f"\n--- [開始] {pattern_name} ({target_str}) ---")

    is_finished = False
    while not is_finished:
        if target_limit and len(collected_uris) >= target_limit:
            break

        if target_limit:
            needed_count = target_limit - len(collected_uris)
            fetch_size = min(current_limit, needed_count)
        else:
            fetch_size = current_limit

        current_offset = len(collected_uris)
        
        batch_success = False
        for attempt in range(1, max_query_retries + 1):
            try:
                query = query_func(fetch_size, current_offset)
                data = {'query': query, 'format': 'json'}
                
                prog_str = f"{len(collected_uris)}/{target_limit}" if target_limit else f"{len(collected_uris)}件〜"
                print(f"[{pattern_name}] Sub-fetch (limit={fetch_size}, progress={prog_str}) ...", end=" ")
                start_time = time.time()

                response = session.post(ENDPOINT, data=data, headers=headers, timeout=timeout_sec)

                if response.status_code in [504, 502, 503, 500]:
                    current_limit = max(20, current_limit // 2)
                    print(f"\n[Server {response.status_code} 負荷警告] 単回LIMITを {current_limit} 件に縮小して即時小分け再リトライします...")
                    time.sleep(2)
                    continue
                elif response.status_code != 200:
                    print(f"\n[Error] Status Code: {response.status_code}")
                    time.sleep(4)
                    continue

                resp_data = response.json()
                bindings = resp_data.get('results', {}).get('bindings', [])

                if not bindings:
                    print("Done (データ上限達成・これ以上結果なし).")
                    batch_success = True
                    is_finished = True
                    break

                current_uris = [b['s']['value'] for b in bindings if 's' in b]
                new_uris = [u for u in current_uris if u not in collected_uris]
                
                if not new_uris:
                    print("Done (重複なしデータエンド).")
                    batch_success = True
                    is_finished = True
                    break

                collected_uris.extend(new_uris)

                elapsed = time.time() - start_time
                total_str = f"{len(collected_uris)}/{target_limit}" if target_limit else f"累計: {len(collected_uris)}件"
                print(f"Got {len(new_uris)} new items. ({total_str}) [{elapsed:.2f}s]")

                if progress_callback:
                    progress_callback(pattern_name, len(collected_uris))

                # 成功したら LIMIT を徐々に元のサイズに戻す
                if current_limit < base_batch_size:
                    current_limit = min(base_batch_size, current_limit * 2)

                # 要求したfetch_sizeより返ってきた件数が少なければ、それが最後のページ
                if len(current_uris) < fetch_size:
                    print(f"[{pattern_name}] 最終バッチ到達（全データ取得完了）。")
                    is_finished = True

                batch_success = True
                break

            except requests.exceptions.ReadTimeout:
                current_limit = max(20, current_limit // 2)
                print(f"\n[応答タイムアウト 試行 {attempt}/{max_query_retries}] LIMITを {current_limit} 件に縮小して小分け再読み込みします。")
                time.sleep(3)
            except Exception as e:
                print(f"\n[通信例外 試行 {attempt}/{max_query_retries}]: {e}")
                time.sleep(3)

        if not batch_success:
            print(f"[{pattern_name}] サブバッチ処理の応答遅延により一時終了。")
            break

        time.sleep(0.5)

    is_success = len(collected_uris) > 0
    time.sleep(1.0)  # 各 Part (クエリパターン) 完了ごとのウェイト
    return collected_uris, is_success


def fetch_deep_graph(uris: list, session: requests.Session = None, timeout_sec: int = 45) -> list:
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得 (BuildMetadata.py 準拠)
    504などのタイムアウトが発生した場合は、自動的にチャンクを半分に分割して再帰取得します。
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

    # 1〜2回通常試行し、ダメなら即座に小分け分割へ移行
    for attempt in range(1, 3):
        try:
            response = session.post(ENDPOINT, data=data, headers=headers, timeout=timeout_sec)
            if response.status_code == 200:
                return response.json().get('results', {}).get('bindings', [])
            elif response.status_code in [504, 502, 503]:
                print(f"[504負荷検知] 全 {len(uris)} 件のグラフ取得で遅延発生。小分け分割へ移行します...")
                break
        except Exception as e:
            print(f"[通信遅延検知]: {e}")
            break
        time.sleep(1)

    # 失敗時、半分のチャンクに小分けにして再帰的にフォールバック取得
    if len(uris) > 1:
        mid = len(uris) // 2
        print(f"-> チャンク分割小分け取得 ({len(uris)} 件 ➔ {mid} 件 + {len(uris) - mid} 件)")
        res1 = fetch_deep_graph(uris[:mid], session, timeout_sec=timeout_sec)
        res2 = fetch_deep_graph(uris[mid:], session, timeout_sec=timeout_sec)
        return res1 + res2

    # 1件単体でも失敗した場合の簡易フォールバック（直下トリプルのみ取得）
    try:
        simple_query = f"""
        CONSTRUCT {{ <{uris[0]}> ?p ?o . }}
        WHERE {{ <{uris[0]}> ?p ?o . }}
        """
        res = session.post(ENDPOINT, data={'query': simple_query, 'format': 'json'}, headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get('results', {}).get('bindings', [])
    except Exception:
        pass

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

            time.sleep(1)

    return processed_count


if __name__ == "__main__":
    print("BuildMetadata.py 準拠の深層メタデータモジュールがロードされました。")
