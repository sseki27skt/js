# -*- coding: utf-8 -*-
"""
MetaClean Studio - ファイル操作 ＆ ヘルパーユーティリティ
"""

import json
import os
import tempfile
import urllib.parse


_line_count_cache = {}

def count_lines(path: str) -> int:
    """指定されたファイルの行数またはJSON要素数を爆速取得（バイナリバッファ＆mtimeキャッシュ）"""
    if not os.path.exists(path):
        return 0
    try:
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        if size == 0:
            return 0
        if path in _line_count_cache and _line_count_cache[path][0] == mtime:
            return _line_count_cache[path][1]

        if path.endswith('.json'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                cnt = len(data) if isinstance(data, list) else 0
        else:
            cnt = 0
            with open(path, 'rb') as f:
                while chunk := f.read(1024 * 1024):
                    cnt += chunk.count(b'\n')
        
        _line_count_cache[path] = (mtime, cnt)
        return cnt
    except Exception:
        return 0


def make_google_link(word: str) -> str:
    """Google検索用のマークダウンリンク文字列を生成"""
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[🔍 Google]({url})"


def make_rich_search_links(word: str) -> dict:
    """各種辞書・検索エンジン・ジャパンサーチのURL辞書を生成"""
    q_google = urllib.parse.quote(f"{word} とは")
    q_wiki = urllib.parse.quote(word)
    q_kotobank = urllib.parse.quote(word)
    q_jps = urllib.parse.quote(word)

    return {
        "google": f"https://www.google.com/search?q={q_google}",
        "wikipedia": f"https://ja.wikipedia.org/wiki/Special:Search?search={q_wiki}",
        "kotobank": f"https://kotobank.jp/word/{q_kotobank}",
        "jps": f"https://jpsearch.go.jp/csearch/jps-item?csid=jps-item&f-about={q_jps}"
    }


def make_rich_search_links_md(word: str) -> str:
    """マークダウン形式の複数検索リンク文字列を生成"""
    links = make_rich_search_links(word)
    return (
        f"[🔍 Google]({links['google']}) ｜ "
        f"[📖 Wikipedia]({links['wikipedia']}) ｜ "
        f"[📚 コトバンク]({links['kotobank']}) ｜ "
        f"[🏛️ ジャパンサーチ]({links['jps']})"
    )


def safe_save_json(data, target_path: str) -> bool:
    """
    データ構造（dict/list等）を一時ファイルに書き出してからアトミックにリネーム保存。
    書き込み途中の破損を防ぐ。
    """
    try:
        dir_name = os.path.dirname(target_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_path, target_path)
        return True
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
