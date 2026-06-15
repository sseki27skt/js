# -*- coding: utf-8 -*-
import urllib.parse
import requests
from bs4 import BeautifulSoup
import time

def search_ddg(query, num_results=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    print(f"URL: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # DuckDuckGo HTML版の検索結果のコンテナ
            items = soup.find_all('div', class_='result')
            print(f"Found items: {len(items)}")
            
            for item in items:
                # タイトルリンク
                title_elem = item.find('a', class_='result__a')
                # スニペット (概要)
                snippet_elem = item.find('a', class_='result__snippet')
                
                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    results.append(f"・{title}\n  {snippet}")
                    if len(results) >= num_results:
                        break
            
            # もしresultが見つからない場合のフォールバック（シンプルなテキスト検索）
            if not results:
                # links_mainなどを探す
                for a in soup.find_all('a', class_='result__snippet'):
                    results.append(a.get_text(strip=True))
                    if len(results) >= num_results:
                        break
            
            return "\n".join(results) if results else "結果が見つかりませんでした。"
        else:
            return f"検索エラー (ステータスコード: {response.status_code})"
    except Exception as e:
        return f"検索エラー: {str(e)}"

if __name__ == "__main__":
    # テストとして「葵氏艶譜 古典籍」を検索
    res = search_ddg("葵氏艶譜 古典籍", 3)
    print("\n--- 検索結果 ---")
    print(res)
