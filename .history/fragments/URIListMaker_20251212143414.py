# pip install --quiet requests pandas tqdm SPARQLWrapper

import requests
import time
import pandas as pd
import os

# =================設定=================
OUTPUT_DIR = "./data"
OUTPUT_FILE = "target_uris_classical_retry.csv"
ENDPOINT = "https://jpsearch.go.jp/rdf/sparql/"
DEFAULT_LIMIT = 500 # 基本の取得件数
# ======================================

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

# --- クエリ生成関数群 (LIMITを引数で受け取るため変更なし) ---

def get_query_ndc(limit, last_uri=None):
    filter_clause = f'FILTER (?s > <{last_uri}>)' if last_uri else ""
    return f"""
    PREFIX schema: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX type: <https://jpsearch.go.jp/term/type/>
    
    SELECT ?s WHERE {{
      ?s rdf:type type:古書・古文書 ;
         schema:about ?ndc .
      FILTER (
        ?ndc IN (<http://jla.or.jp/data/ndc#014.7>, <http://jla.or.jp/data/ndc#186.5>, <http://jla.or.jp/data/ndc#774.7>) || 
        STRSTARTS(STR(?ndc), "http://jla.or.jp/data/ndc#76")
      )
      {filter_clause}
    }}
    ORDER BY ?s
    LIMIT {limit}
    """

def get_query_label_only(limit, last_uri=None):
    filter_clause = f'FILTER (?s > <{last_uri}>)' if last_uri else ""
    return f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX type: <https://jpsearch.go.jp/term/type/>
    
    SELECT ?s WHERE {{
      ?s rdf:type type:古書・古文書 ;
         rdfs:label ?label .
      FILTER (REGEX(?label, "譜|音楽|樂譜", "i"))
      {filter_clause}
    }}
    ORDER BY ?s
    LIMIT {limit}
    """

def get_query_name_only(limit, last_uri=None):
    filter_clause = f'FILTER (?s > <{last_uri}>)' if last_uri else ""
    return f"""
    PREFIX schema: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX type: <https://jpsearch.go.jp/term/type/>
    
    SELECT ?s WHERE {{
      ?s rdf:type type:古書・古文書 ;
         schema:name ?name .
      FILTER (REGEX(?name, "譜|音楽|樂譜", "i"))
      {filter_clause}
    }}
    ORDER BY ?s
    LIMIT {limit}
    """

def get_query_desc(limit, last_uri=None):
    filter_clause = f'FILTER (?s > <{last_uri}>)' if last_uri else ""
    return f"""
    PREFIX schema: <http://schema.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX type: <https://jpsearch.go.jp/term/type/>
    
    SELECT ?s WHERE {{
      ?s rdf:type type:古書・古文書 ;
         schema:description ?desc .
      FILTER (REGEX(?desc, "楽譜|樂譜|音楽", "i"))
      {filter_clause}
    }}
    ORDER BY ?s
    LIMIT {limit}
    """

# --- 実行ロジック (ここを大幅強化) ---

def fetch_uris_by_pattern(query_func, pattern_name):
    collected_uris = []
    last_uri = None
    
    # 動的に変更するパラメータ
    current_limit = DEFAULT_LIMIT
    retry_count = 0
    MAX_RETRIES = 5
    
    print(f"\n--- [開始] {pattern_name} ---")
    
    while True:
        # 現在のlimitを使ってクエリ生成
        query = query_func(current_limit, last_uri)
        params = {'query': query, 'format': 'json'}
        
        try:
            cursor_info = str(last_uri)[-20:] if last_uri else 'START'
            print(f"[{pattern_name}] Fetching (limit={current_limit}) after: ...{cursor_info} ...", end=" ")
            start_time = time.time()
            
            response = requests.get(ENDPOINT, params=params, timeout=60)
            
            # --- エラー処理 (リトライロジック) ---
            if response.status_code != 200:
                print(f"\n[Error] Status Code: {response.status_code}")
                retry_count += 1
                
                if retry_count > MAX_RETRIES:
                    print(f"!!! リトライ回数上限 ({MAX_RETRIES}) に達しました。このパターンを中断します。 !!!")
                    break
                
                # LIMITを半分にして負荷を下げる（最小50）
                old_limit = current_limit
                current_limit = max(50, current_limit // 2)
                
                wait_time = 10 * retry_count # 10秒, 20秒, 30秒...と待機時間を増やす
                print(f"-> 待機 {wait_time}秒... 次回は LIMITを {old_limit} -> {current_limit} に減らして再試行します。")
                
                time.sleep(wait_time)
                continue # ループの先頭に戻って再試行（breakしない！）

            # --- 成功時の処理 ---
            data = response.json()
            bindings = data['results']['bindings']
            
            # リトライ成功したらカウンタとLIMITをリセット（または徐々に戻す）
            if retry_count > 0:
                print(f" [復帰成功] ", end="")
                retry_count = 0
                current_limit = DEFAULT_LIMIT # 成功したので元に戻す
            
            if not bindings:
                print("Done (No more results).")
                break
            
            current_uris = [b['s']['value'] for b in bindings]
            collected_uris.extend(current_uris)
            
            elapsed = time.time() - start_time
            print(f"Got {len(current_uris)} items. (Subtotal: {len(collected_uris)}) [{elapsed:.2f}s]")
            
            last_uri = current_uris[-1]
            
            # 取得数が現在のLIMIT未満なら最終ページとみなす
            if len(current_uris) < current_limit:
                print(f"Last batch for {pattern_name}.")
                break
            
            # 正常時は1秒待機
            time.sleep(1) 
            
        except Exception as e:
            print(f"\n[Exception] {e}")
            retry_count += 1
            if retry_count > MAX_RETRIES:
                break
            time.sleep(10)
            
    return collected_uris

def main():
    ensure_dir(OUTPUT_DIR)
    
    all_unique_uris = set()
    
    patterns = [
        ("1. NDC分類検索", get_query_ndc),
        ("2. タイトル(Label)検索", get_query_label_only),
        ("3. 名称(Name)検索", get_query_name_only),
        ("4. 説明文(Desc)検索", get_query_desc)
    ]
    
    for name, func in patterns:
        uris = fetch_uris_by_pattern(func, name)
        
        before_count = len(all_unique_uris)
        all_unique_uris.update(uris)
        after_count = len(all_unique_uris)
        
        print(f"-> {name} 結果: {len(uris)} 件 (新規ユニーク: {after_count - before_count} 件)")
        time.sleep(2)

    if all_unique_uris:
        sorted_uris = sorted(list(all_unique_uris))
        df = pd.DataFrame(sorted_uris, columns=['uri'])
        save_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
        df.to_csv(save_path, index=False)
        print(f"\n=== 全工程完了 ===")
        print(f"保存完了: {save_path}")
        print(f"最終総件数: {len(sorted_uris)}")
    else:
        print("\nデータが見つかりませんでした。")

if __name__ == "__main__":
    main()
    