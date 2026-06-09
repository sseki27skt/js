import requests
import time
import json
import os
from tqdm import tqdm
from collections import defaultdict

# =================設定=================
INPUT_FILE = "./data/target_uris_classical_retry.csv"
OUTPUT_FILE = "./data/classical_scores_dynamic.jsonl"
ENDPOINT = "https://jpsearch.go.jp/rdf/sparql/"
BATCH_SIZE = 20
# ======================================

# URIを短縮してキーにするためのマッピング
PREFIX_MAP = {
    "http://schema.org/": "schema:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://purl.org/dc/terms/": "dct:",
    "https://jpsearch.go.jp/term/property/": "jps:",
    "http://www.w3.org/2002/07/owl#": "owl:",
    "http://www.w3.org/2004/02/skos/core#": "skos:"
}

def shorten_uri(uri):
    """
    長いURIをPrefix付きの短い文字列に変換する
    例: http://schema.org/name -> schema:name
    """
    for prefix, short in PREFIX_MAP.items():
        if uri.startswith(prefix):
            return uri.replace(prefix, short)
    return uri # マッチしなければそのまま

def fetch_deep_graph(uris):
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得
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
    try:
        response = requests.get(ENDPOINT, params=params, timeout=60)
        if response.status_code == 200:
            return response.json()['results']['bindings']
    except Exception as e:
        print(f"Error: {e}")
    return []

def parse_dynamic(bindings, target_uris):
    # 1. グラフ構築
    graph = defaultdict(lambda: defaultdict(list))
    for b in bindings:
        s = b['s']['value']
        p = b['p']['value']
        o = b['o']['value']
        graph[s][p].append(o)
    
    results = []
    
    for uri in target_uris:
        if uri not in graph:
            results.append({"uri": uri, "status": "failed"})
            continue
            
        # 再帰的に辞書を構築する関数
        # visitedを使って循環参照による無限ループを防ぐ
        def node_to_dict(current_node, visited=None):
            if visited is None: visited = set()
            
            if current_node in visited:
                return {"@id": current_node, "meta": "cyclic_reference"}
            
            visited.add(current_node)
            
            # このノードが持つプロパティを取得
            props = graph.get(current_node, {})
            node_data = {}
            
            # @id (URI) を明記
            node_data["@id"] = current_node
            
            for p_uri, objects in props.items():
                short_p = shorten_uri(p_uri) # キーを短縮 (例: schema:name)
                
                parsed_objects = []
                for obj in objects:
                    # オブジェクトがグラフ内に存在し、かつ親URIに関連するサブノードであれば展開
                    # (外部の独立したURIなら展開せずリンクとして扱う)
                    if obj in graph and (obj.startswith(uri) or obj.startswith("_:")):
                        # 再帰呼び出し（ネストさせる）
                        parsed_objects.append(node_to_dict(obj, visited.copy()))
                    else:
                        # 文字列または外部URIとしてそのまま保持
                        parsed_objects.append(obj)
                
                # リストが1つだけなら展開するか？ -> 今回はデータの一貫性のためリストのままにするか、
                # 分析のしやすさを優先して「値が1つなら直値、複数ならリスト」にするのが一般的
                if len(parsed_objects) == 1:
                    node_data[short_p] = parsed_objects[0]
                else:
                    node_data[short_p] = parsed_objects

            return node_data

        # メイン処理：このURIをルートとしてツリーを作る
        structured_data = node_to_dict(uri)
        structured_data["status"] = "success" # 成功フラグ
        
        results.append(structured_data)
        
    return results

def main():
    if not os.path.exists(INPUT_FILE):
        return

    df = pd.read_csv(INPUT_FILE)
    all_uris = df['uri'].tolist()
    total = len(all_uris)
    
    # 既存チェック
    start_idx = 0
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            start_idx = sum(1 for _ in f)
        if start_idx > 0:
            print(f"再開: {start_idx} 件目から")

    print(f"動的メタデータ収集開始: {total} 件")
    
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        with tqdm(total=total, initial=start_idx, unit="uri") as pbar:
            for i in range(start_idx, total, BATCH_SIZE):
                batch_uris = all_uris[i : i + BATCH_SIZE]
                if not batch_uris: break
                
                bindings = fetch_deep_graph(batch_uris)
                items = parse_dynamic(bindings, batch_uris)
                
                for item in items:
                    json.dump(item, f, ensure_ascii=False)
                    f.write('\n')
                
                f.flush()
                pbar.update(len(batch_uris))
                time.sleep(2)

if __name__ == "__main__":
    main()