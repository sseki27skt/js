# -*- coding: utf-8 -*-
import os
import shutil

# 移行（インポート）対象のファイルマッピング
# (コピー元パス, コピー先パス)
ASSET_MAPPING = {
    # 収集データ
    "data/target_uris_classical_retry.csv": "integrated_portal/pipeline_steps/01_data_collection/target_uris.csv",
    "data/classical_scores_dynamic.jsonl": "integrated_portal/pipeline_steps/01_data_collection/raw_metadata.jsonl",
    
    # ルールベース
    "02_rule_based_filtering/about_rules.json": "integrated_portal/rules/about_rules.json",
    "02_rule_based_filtering/suffix_rules.json": "integrated_portal/rules/suffix_rules.json",
    
    # N-gram仕分けルール
    "fragments/ngram/ok_word_list.txt": "integrated_portal/rules/ok_word_list.txt",
    "fragments/ngram/ng_word_list.txt": "integrated_portal/rules/ng_word_list.txt",
    
    # 必要に応じて中間データも流用
    "data/classical_scores_about_filtered.jsonl": "integrated_portal/pipeline_steps/02_rule_based_filtering/about_filtered.jsonl",
    "data/classical_scores_suffix_filtered.jsonl": "integrated_portal/pipeline_steps/03_hybrid_classification/suffix_filtered.jsonl",
    
    # N-gram集計データ（手戻り発生時に再利用可能）
    "fragments/ngram/keyword_mining_ranking.csv": "integrated_portal/pipeline_steps/03_hybrid_classification/ngram_ranking.csv",
    "fragments/ngram/keyword_samples.json": "integrated_portal/pipeline_steps/03_hybrid_classification/ngram_samples.json",
}

def import_existing_assets(overwrite=False):
    """
    既存のデータおよびルールファイルを新環境（integrated_portal/）に安全にコピー（インポート）します。
    元ファイルは一切移動・変更・削除されません。
    """
    results = []
    
    for src, dest in ASSET_MAPPING.items():
        # コピー元が存在しない場合はスキップ
        if not os.path.exists(src):
            results.append({"file": src, "status": "skipped_not_found", "message": "元ファイルが存在しません。"})
            continue
            
        # コピー先ディレクトリの自動作成
        dest_dir = os.path.dirname(dest)
        os.makedirs(dest_dir, exist_ok=True)
        
        # コピー先がすでに存在し、上書き無効の場合はスキップ
        if os.path.exists(dest) and not overwrite:
            results.append({"file": dest, "status": "skipped_exists", "message": "インポート先に既に存在します（上書きスキップ）。"})
            continue
            
        try:
            # 安全に複製（メタデータも含めてコピー）
            shutil.copy2(src, dest)
            results.append({"file": dest, "status": "imported", "message": "正常にインポート（コピー）されました。"})
        except Exception as e:
            results.append({"file": dest, "status": "failed", "message": f"コピー失敗: {str(e)}"})
            
    return results

def get_import_status():
    """
    主要なデータ・ルールの新環境への移行状況をチェックします。
    """
    status = {}
    for src, dest in ASSET_MAPPING.items():
        key = os.path.basename(dest)
        status[key] = {
            "source_exists": os.path.exists(src),
            "dest_exists": os.path.exists(dest),
            "dest_path": dest
        }
    return status

def copy_static_search_assets(export_dir):
    """
    静的資料検索ツールのHTML、CSS、JavaScriptファイルをエクスポート先に書き出します。
    """
    os.makedirs(export_dir, exist_ok=True)
    
    # HTMLのテンプレート
    html_content = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="ジャパンサーチの古典籍カテゴリから高精度に抽出された日本音楽の楽譜資料データベースです。雅楽、声明、能楽、三味線音楽、琵琶楽、尺八楽などの資料をジャンルや楽器から快適に検索・絞り込みできます。">
    <title>日本音楽楽譜デジタルアーカイブ | 古典籍資料検索</title>
    <!-- Google Fonts: Noto Serif JP & Montserrat -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600&family=Noto+Serif+JP:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header class="hero-header">
        <div class="header-overlay"></div>
        <div class="header-container">
            <span class="sub-title">JAPAN SEARCH CLASSICAL SCORES</span>
            <h1>日本音楽楽譜デジタルアーカイブ</h1>
            <p class="description">古典籍に眠る雅楽、声明、能楽、邦楽楽譜資料の検索・閲覧ポータル</p>
        </div>
    </header>

    <main class="main-layout">
        <!-- 検索・フィルタサイドバー -->
        <aside class="filter-sidebar">
            <div class="sidebar-sticky">
                <div class="search-box">
                    <label for="keyword-search">キーワード検索</label>
                    <div class="search-input-wrapper">
                        <input type="text" id="keyword-search" placeholder="資料名、説明文などから検索...">
                        <span class="search-icon">🔍</span>
                    </div>
                </div>

                <div class="filter-group">
                    <h3>ジャンルから探す</h3>
                    <div class="genre-accordion-list" id="genre-filters">
                        <!-- JSで動的にアコーディオンを生成 -->
                    </div>
                </div>

                <div class="filter-group">
                    <h3>使用楽器</h3>
                    <div class="checkbox-list" id="instrument-filters">
                        <!-- JSで動的に生成 -->
                    </div>
                </div>

                <div class="filter-group">
                    <h3>所蔵先・提供元</h3>
                    <div class="checkbox-list" id="provider-filters">
                        <!-- JSで動的に生成 -->
                    </div>
                </div>

                <button id="btn-reset-filters" class="btn btn-secondary btn-full">条件をリセット</button>
            </div>
        </aside>

        <!-- メインコンテンツ -->
        <section class="results-content">
            <div class="results-header">
                <div class="results-stats">
                    見つかった資料: <span id="match-count" class="highlight">0</span> 件 / 全 <span id="total-count">0</span> 件
                </div>
                <div class="view-controls">
                    <label for="sort-select">並び順: </label>
                    <select id="sort-select">
                        <option value="title-asc">タイトル順 (昇順)</option>
                        <option value="title-desc">タイトル順 (降順)</option>
                    </select>
                </div>
            </div>

            <!-- スケルトンローダー (読み込み中表示) -->
            <div id="skeleton-loader" class="cards-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>

            <!-- カードグリッド -->
            <div id="cards-grid" class="cards-grid hide">
                <!-- JSで動的に生成 -->
            </div>

            <!-- ページネーション -->
            <div class="pagination-container" id="pagination">
                <!-- JSで動的に生成 -->
            </div>
        </section>
    </main>

    <!-- 詳細モーダル -->
    <div id="detail-modal" class="modal-overlay hide">
        <div class="modal-window">
            <button class="modal-close" id="btn-close-modal">&times;</button>
            <div class="modal-content-grid">
                <div class="modal-image-area" id="modal-image-container">
                    <!-- 画像またはデフォルトSVG -->
                </div>
                <div class="modal-info-area">
                    <span class="modal-sub" id="modal-provider"></span>
                    <h2 class="modal-title" id="modal-title">資料名</h2>
                    <div class="modal-badges" id="modal-badges">
                        <!-- ジャンル・楽器バッジ -->
                    </div>
                    <div class="modal-description-wrapper">
                        <h3>説明・詳細</h3>
                        <p class="modal-description" id="modal-description">説明文</p>
                    </div>
                    <div class="modal-actions">
                        <a href="#" target="_blank" id="btn-link-original" class="btn btn-primary">原本を見る (外部サイト)</a>
                        <a href="#" target="_blank" id="btn-link-jpsearch" class="btn btn-secondary">ジャパンサーチで見る</a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <footer class="main-footer">
        <div class="footer-container">
            <p>データ提供: <a href="https://jpsearch.go.jp/" target="_blank">ジャパンサーチ (JAPAN SEARCH)</a></p>
            <p>&copy; 2026 日本音楽楽譜デジタルアーカイブプロジェクト. All Rights Reserved.</p>
        </div>
    </footer>

    <script src="search.js"></script>
</body>
</html>
"""

    # CSSのテンプレート (和モダンプレミアム)
    css_content = """/* CSS Reset & Variables */
:root {
    --bg-dark: #121212;
    --bg-panel: rgba(28, 28, 30, 0.75);
    --bg-card: rgba(38, 38, 41, 0.5);
    --text-primary: #f5f5f7;
    --text-secondary: #a1a1a6;
    --accent-gold: #c5a059;
    --accent-gold-hover: #e5bf73;
    --accent-red: #a63a2b;
    --border-color: rgba(255, 255, 255, 0.08);
    --border-color-hover: rgba(197, 160, 89, 0.4);
    --font-serif: 'Noto Serif JP', serif;
    --font-sans: 'Montserrat', 'Noto Sans JP', sans-serif;
    --card-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
    --glass-blur: blur(16px);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background-color: var(--bg-dark);
    color: var(--text-primary);
    font-family: var(--font-sans);
    line-height: 1.6;
    overflow-x: hidden;
}

a {
    color: var(--accent-gold);
    text-decoration: none;
    transition: color 0.2s;
}
a:hover {
    color: var(--accent-gold-hover);
}

/* Header */
.hero-header {
    position: relative;
    height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    background: linear-gradient(135deg, #1f140e 0%, #0c0806 100%);
    border-bottom: 2px solid var(--accent-gold);
    overflow: hidden;
}

/* 青海波をCSS背景で薄く描画 */
.hero-header::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    opacity: 0.08;
    background-image: radial-gradient(circle at 100% 150%, transparent 24%, var(--accent-gold) 24%, var(--accent-gold) 28%, transparent 28%, transparent),
                      radial-gradient(circle at 0% 150%, transparent 24%, var(--accent-gold) 24%, var(--accent-gold) 28%, transparent 28%, transparent),
                      radial-gradient(circle at 50% 100%, transparent 4%, var(--accent-gold) 4%, var(--accent-gold) 8%, transparent 8%, transparent),
                      radial-gradient(circle at 100% 50%, transparent 4%, var(--accent-gold) 4%, var(--accent-gold) 8%, transparent 8%, transparent),
                      radial-gradient(circle at 0% 50%, transparent 4%, var(--accent-gold) 4%, var(--accent-gold) 8%, transparent 8%, transparent);
    background-size: 80px 40px;
}

.header-container {
    position: relative;
    z-index: 2;
    max-width: 800px;
    padding: 0 20px;
}

.hero-header h1 {
    font-family: var(--font-serif);
    font-size: clamp(1.6rem, 5vw, 2.6rem);
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--text-primary);
    margin-bottom: 10px;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.8);
    word-break: keep-all;
}

.hero-header .sub-title {
    font-size: 0.9rem;
    font-weight: 600;
    letter-spacing: 0.3em;
    color: var(--accent-gold);
    display: block;
    margin-bottom: 5px;
}

.hero-header .description {
    font-family: var(--font-serif);
    font-size: 1.1rem;
    color: var(--text-secondary);
    letter-spacing: 0.05em;
}

/* Layout */
.main-layout {
    display: flex;
    max-width: 1400px;
    margin: 40px auto;
    padding: 0 20px;
    gap: 30px;
}

/* Sidebar */
.filter-sidebar {
    width: 320px;
    flex-shrink: 0;
}

.sidebar-sticky {
    position: sticky;
    top: 30px;
    background: var(--bg-panel);
    backdrop-filter: var(--glass-blur);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 24px;
    box-shadow: var(--card-shadow);
}

.search-box {
    margin-bottom: 24px;
}

.search-box label {
    display: block;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    margin-bottom: 8px;
}

.search-input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
}

.search-input-wrapper input {
    width: 100%;
    padding: 12px 40px 12px 14px;
    background-color: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.95rem;
    transition: all 0.3s;
}

.search-input-wrapper input:focus {
    outline: none;
    border-color: var(--accent-gold);
    box-shadow: 0 0 10px rgba(197, 160, 89, 0.2);
}

.search-icon {
    position: absolute;
    right: 14px;
    color: var(--text-secondary);
    pointer-events: none;
}

.filter-group {
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 20px;
}

.filter-group:last-of-type {
    border-bottom: none;
    padding-bottom: 0;
}

.filter-group h3 {
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--accent-gold);
    margin-bottom: 14px;
}

.checkbox-list {
    max-height: 200px;
    overflow-y: auto;
    padding-right: 5px;
}

/* Custom Scrollbar */
.checkbox-list::-webkit-scrollbar,
.genre-accordion-content::-webkit-scrollbar {
    width: 5px;
}
.checkbox-list::-webkit-scrollbar-thumb,
.genre-accordion-content::-webkit-scrollbar-thumb {
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
}

.checkbox-item {
    display: flex;
    align-items: flex-start;
    margin-bottom: 10px;
    cursor: pointer;
    font-size: 0.88rem;
    color: var(--text-secondary);
    transition: color 0.2s;
}

.checkbox-item:hover {
    color: var(--text-primary);
}

.checkbox-item input {
    margin-top: 3px;
    margin-right: 10px;
    cursor: pointer;
    accent-color: var(--accent-gold);
}

/* Genre Accordion */
.genre-accordion-item {
    margin-bottom: 8px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-color);
    overflow: hidden;
}

.genre-accordion-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    transition: background-color 0.2s;
}

.genre-accordion-header:hover {
    background-color: rgba(255, 255, 255, 0.04);
}

.genre-accordion-header-left {
    display: flex;
    align-items: center;
}

.genre-accordion-header-left input {
    margin-right: 10px;
    accent-color: var(--accent-gold);
}

.genre-accordion-toggle-icon {
    font-size: 0.75rem;
    transition: transform 0.2s;
    color: var(--text-secondary);
}

.genre-accordion-item.active .genre-accordion-toggle-icon {
    transform: rotate(90deg);
}

.genre-accordion-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.25s ease-out;
    background: rgba(0, 0, 0, 0.15);
    padding: 0 14px;
}

.genre-accordion-item.active .genre-accordion-content {
    max-height: 200px;
    overflow-y: auto;
    padding: 10px 14px;
}

/* Results Area */
.results-content {
    flex-grow: 1;
}

.results-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 14px 20px;
}

.results-stats {
    font-size: 0.95rem;
    color: var(--text-secondary);
}

.results-stats .highlight {
    color: var(--accent-gold);
    font-weight: 600;
    font-size: 1.1rem;
}

.view-controls select {
    background-color: var(--bg-dark);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-primary);
    padding: 6px 12px;
    font-size: 0.88rem;
    outline: none;
    cursor: pointer;
}

.view-controls select:focus {
    border-color: var(--accent-gold);
}

/* Cards Grid */
.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 24px;
    margin-bottom: 40px;
}

.cards-grid.hide {
    display: none;
}

/* Card */
.score-card {
    background: var(--bg-card);
    backdrop-filter: var(--glass-blur);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    cursor: pointer;
}

.score-card:hover {
    transform: translateY(-5px);
    border-color: var(--border-color-hover);
    box-shadow: 0 10px 30px rgba(197, 160, 89, 0.15);
}

.card-image-wrapper {
    position: relative;
    width: 100%;
    height: 180px;
    background-color: rgba(0, 0, 0, 0.4);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    border-bottom: 1px solid var(--border-color);
}

.card-image-wrapper img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.5s;
}

.score-card:hover .card-image-wrapper img {
    transform: scale(1.05);
}

/* SVGプレースホルダー背景 */
.card-placeholder-bg {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #1d1d1f 0%, #111 100%);
    position: relative;
}

.card-placeholder-bg::after {
    content: "譜";
    font-family: var(--font-serif);
    font-size: 5rem;
    color: rgba(197, 160, 89, 0.06);
    position: absolute;
}

.card-placeholder-bg svg {
    width: 60px;
    height: 60px;
    fill: var(--accent-gold);
    opacity: 0.45;
    z-index: 2;
}

.card-info {
    padding: 20px;
    display: flex;
    flex-direction: column;
    flex-grow: 1;
}

.card-provider {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--accent-gold);
    letter-spacing: 0.05em;
    margin-bottom: 6px;
    text-transform: uppercase;
}

.card-title {
    font-family: var(--font-serif);
    font-size: 1.15rem;
    font-weight: 700;
    line-height: 1.4;
    color: var(--text-primary);
    margin-bottom: 12px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    height: 3.2em;
}

.card-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 16px;
}

.badge {
    display: inline-block;
    padding: 4px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    border-radius: 4px;
    letter-spacing: 0.02em;
}

.badge-genre {
    background-color: rgba(197, 160, 89, 0.15);
    color: var(--accent-gold-hover);
    border: 1px solid rgba(197, 160, 89, 0.25);
}

.badge-instrument {
    background-color: rgba(255, 255, 255, 0.04);
    color: var(--text-secondary);
    border: 1px solid var(--border-color);
}

.card-description {
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 20px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    height: 4.5em;
}

.card-footer {
    margin-top: auto;
    display: flex;
    justify-content: flex-end;
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 18px;
    font-size: 0.88rem;
    font-weight: 600;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-sans);
}

.btn-full {
    width: 100%;
}

.btn-primary {
    background-color: var(--accent-gold);
    color: #000;
}
.btn-primary:hover {
    background-color: var(--accent-gold-hover);
    box-shadow: 0 0 15px rgba(197, 160, 89, 0.3);
}

.btn-secondary {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
}
.btn-secondary:hover {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: var(--text-secondary);
}

/* Pagination */
.pagination-container {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-top: 20px;
}

.page-btn {
    width: 38px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    background-color: var(--bg-card);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
}

.page-btn:hover:not(.disabled):not(.active) {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
    border-color: var(--text-secondary);
}

.page-btn.active {
    background-color: var(--accent-gold);
    color: #000;
    border-color: var(--accent-gold);
}

.page-btn.disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

/* Skeleton Loading */
.skeleton-card {
    height: 380px;
    background: linear-gradient(90deg, rgba(255,255,255,0.02) 25%, rgba(255,255,255,0.05) 50%, rgba(255,255,255,0.02) 75%);
    background-size: 200% 100%;
    animation: loading 1.5s infinite;
    border-radius: 10px;
    border: 1px solid var(--border-color);
}

@keyframes loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* Modal Overlay */
.modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 1;
    transition: opacity 0.3s;
}

.modal-overlay.hide {
    display: none;
    opacity: 0;
}

.modal-window {
    background: #18181a;
    border: 1px solid var(--border-color-hover);
    border-radius: 12px;
    width: 90%;
    max-width: 900px;
    max-height: 85vh;
    overflow-y: auto;
    position: relative;
    box-shadow: 0 10px 50px rgba(0, 0, 0, 0.7);
    animation: modalSlide 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

@keyframes modalSlide {
    from { transform: translateY(30px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
}

.modal-close {
    position: absolute;
    top: 15px; right: 20px;
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 2rem;
    cursor: pointer;
    z-index: 10;
    transition: color 0.2s;
}
.modal-close:hover {
    color: var(--text-primary);
}

.modal-content-grid {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    min-height: 450px;
}

.modal-image-area {
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    border-right: 1px solid var(--border-color);
    padding: 30px;
    position: relative;
}

.modal-image-area img {
    max-width: 100%;
    max-height: 60vh;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
}

.modal-image-area .modal-placeholder svg {
    width: 120px;
    height: 120px;
    fill: var(--accent-gold);
    opacity: 0.3;
}

.modal-info-area {
    padding: 40px;
    display: flex;
    flex-direction: column;
}

.modal-provider {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent-gold);
    letter-spacing: 0.1em;
    margin-bottom: 8px;
    text-transform: uppercase;
}

.modal-title {
    font-family: var(--font-serif);
    font-size: 1.8rem;
    font-weight: 700;
    line-height: 1.3;
    color: var(--text-primary);
    margin-bottom: 16px;
}

.modal-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 24px;
}

.modal-description-wrapper {
    margin-bottom: 30px;
    flex-grow: 1;
}

.modal-description-wrapper h3 {
    font-size: 0.95rem;
    color: var(--accent-gold);
    border-left: 2px solid var(--accent-gold);
    padding-left: 10px;
    margin-bottom: 12px;
}

.modal-description {
    font-size: 0.92rem;
    color: var(--text-secondary);
    line-height: 1.7;
    white-space: pre-wrap;
}

.modal-actions {
    display: flex;
    gap: 12px;
}

/* Footer */
.main-footer {
    background-color: #0b0b0c;
    border-top: 1px solid var(--border-color);
    padding: 40px 0;
    text-align: center;
    font-size: 0.82rem;
    color: var(--text-secondary);
}

.footer-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

.main-footer p {
    margin-bottom: 8px;
}

/* Responsive */
@media (max-width: 1024px) {
    .main-layout {
        flex-direction: column;
    }
    .filter-sidebar {
        width: 100%;
    }
    .sidebar-sticky {
        position: static;
    }
}

@media (max-width: 768px) {
    .hero-header h1 {
        font-size: 2rem;
    }
    .modal-content-grid {
        grid-template-columns: 1fr;
    }
    .modal-image-area {
        border-right: none;
        border-bottom: 1px solid var(--border-color);
        padding: 20px;
    }
    .modal-info-area {
        padding: 24px;
    }
    .modal-actions {
        flex-direction: column;
    }
}
"""

    # JSのテンプレート (データ読み込み・検索)
    js_content = """// Variables & Setup
let scoresData = [];
let filteredData = [];
let currentPage = 1;
const itemsPerPage = 12;

// DOM Elements
const keywordInput = document.getElementById('keyword-search');
const genreContainer = document.getElementById('genre-filters');
const instrumentContainer = document.getElementById('instrument-filters');
const providerContainer = document.getElementById('provider-filters');
const matchCountEl = document.getElementById('match-count');
const totalCountEl = document.getElementById('total-count');
const sortSelect = document.getElementById('sort-select');
const cardsGrid = document.getElementById('cards-grid');
const skeletonLoader = document.getElementById('skeleton-loader');
const paginationContainer = document.getElementById('pagination');
const btnReset = document.getElementById('btn-reset-filters');

// Modal Elements
const detailModal = document.getElementById('detail-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const modalTitle = document.getElementById('modal-title');
const modalDescription = document.getElementById('modal-description');
const modalProvider = document.getElementById('modal-provider');
const modalImageContainer = document.getElementById('modal-image-container');
const modalBadges = document.getElementById('modal-badges');
const btnLinkOriginal = document.getElementById('btn-link-original');
const btnLinkJpSearch = document.getElementById('btn-link-jpsearch');

// SVG Musical Note for placeholder
const placeholderSvg = `<div class="card-placeholder-bg">
    <svg viewBox="0 0 24 24">
        <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
    </svg>
</div>`;

// Init App
document.addEventListener('DOMContentLoaded', init);

async function init() {
    setupEventHandlers();
    try {
        const response = await fetch('scores_data.json');
        if (!response.ok) throw new Error('Data load failed');
        scoresData = await response.json();
        
        filteredData = [...scoresData];
        totalCountEl.textContent = scoresData.length;
        
        buildFilterSelectors();
        applyFilters();
        
        skeletonLoader.classList.add('hide');
        cardsGrid.classList.remove('hide');
    } catch (error) {
        console.error('Error initializing search app:', error);
        skeletonLoader.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--accent-red);">
            <h3>データの読み込みに失敗しました</h3>
            <p>サーバーまたはローカルホスト経由でアクセスしているかご確認ください。</p>
        </div>`;
    }
}

function setupEventHandlers() {
    keywordInput.addEventListener('input', () => { currentPage = 1; applyFilters(); });
    sortSelect.addEventListener('change', () => { applyFilters(); });
    btnReset.addEventListener('click', resetFilters);
    btnCloseModal.addEventListener('click', closeModal);
    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) closeModal();
    });
    
    // ESC key closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

// Build Filter Checkboxes Dynamically
function buildFilterSelectors() {
    // Collect all genres, instruments, and providers
    const genresMap = new Map(); // 大ジャンル -> Set of サブジャンル
    const instrumentsSet = new Set();
    const providersSet = new Set();
    
    scoresData.forEach(item => {
        // Genre
        if (item.genre) {
            if (!genresMap.has(item.genre)) {
                genresMap.set(item.genre, new Set());
            }
            if (item.subgenre) {
                genresMap.get(item.genre).add(item.subgenre);
            }
        }
        // Instruments
        if (Array.isArray(item.instruments)) {
            item.instruments.forEach(inst => { if (inst) instrumentsSet.add(inst); });
        }
        // Provider
        if (item.provider) {
            providersSet.add(item.provider);
        }
    });

    // 1. Build Genre Accordion
    genreContainer.innerHTML = '';
    Array.from(genresMap.keys()).sort().forEach(genre => {
        const subgenres = Array.from(genresMap.get(genre)).sort();
        
        const accordionItem = document.createElement('div');
        accordionItem.className = 'genre-accordion-item';
        
        const header = document.createElement('div');
        header.className = 'genre-accordion-header';
        
        const left = document.createElement('div');
        left.className = 'genre-accordion-header-left';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = genre;
        checkbox.dataset.filterType = 'genre';
        checkbox.addEventListener('change', (e) => {
            // 親チェックの変更で子チェックも連動
            const children = accordionItem.querySelectorAll('.genre-sub-checkbox');
            children.forEach(child => child.checked = e.target.checked);
            currentPage = 1;
            applyFilters();
        });
        
        const label = document.createElement('span');
        label.textContent = genre;
        
        left.appendChild(checkbox);
        left.appendChild(label);
        header.appendChild(left);
        
        if (subgenres.length > 0) {
            const arrow = document.createElement('span');
            arrow.className = 'genre-accordion-toggle-icon';
            arrow.textContent = '▶';
            header.appendChild(arrow);
            
            // アコーディオンのトグル動作 (ラベルクリック等)
            label.addEventListener('click', (e) => {
                e.stopPropagation();
                accordionItem.classList.toggle('active');
                arrow.textContent = accordionItem.classList.contains('active') ? '▼' : '▶';
            });
            arrow.addEventListener('click', (e) => {
                e.stopPropagation();
                accordionItem.classList.toggle('active');
                arrow.textContent = accordionItem.classList.contains('active') ? '▼' : '▶';
            });
        }
        
        accordionItem.appendChild(header);
        
        if (subgenres.length > 0) {
            const content = document.createElement('div');
            content.className = 'genre-accordion-content';
            
            subgenres.forEach(sub => {
                const subItem = document.createElement('label');
                subItem.className = 'checkbox-item';
                
                const subCheckbox = document.createElement('input');
                subCheckbox.type = 'checkbox';
                subCheckbox.value = sub;
                subCheckbox.className = 'genre-sub-checkbox';
                subCheckbox.dataset.parentGenre = genre;
                subCheckbox.dataset.filterType = 'subgenre';
                subCheckbox.addEventListener('change', () => {
                    // 子のチェック状態から親のチェック状態を制御
                    const allSubs = accordionItem.querySelectorAll('.genre-sub-checkbox');
                    const checkedSubs = accordionItem.querySelectorAll('.genre-sub-checkbox:checked');
                    checkbox.checked = checkedSubs.length > 0;
                    currentPage = 1;
                    applyFilters();
                });
                
                const subText = document.createTextNode(sub);
                subItem.appendChild(subCheckbox);
                subItem.appendChild(subText);
                content.appendChild(subItem);
            });
            
            accordionItem.appendChild(content);
        }
        
        genreContainer.appendChild(accordionItem);
    });

    // 2. Build Instruments Checkboxes
    instrumentContainer.innerHTML = '';
    Array.from(instrumentsSet).sort().forEach(inst => {
        const item = createCheckboxItem(inst, 'instrument');
        instrumentContainer.appendChild(item);
    });

    // 3. Build Providers Checkboxes
    providerContainer.innerHTML = '';
    Array.from(providersSet).sort().forEach(prov => {
        const labelText = prov.replace('ADEAC', 'ADEAC (地域特化型アーカイブ)').replace('NDLサーチ', '国立国会図書館');
        const item = createCheckboxItem(prov, 'provider', labelText);
        providerContainer.appendChild(item);
    });
}

function createCheckboxItem(value, type, labelText = null) {
    const item = document.createElement('label');
    item.className = 'checkbox-item';
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = value;
    checkbox.dataset.filterType = type;
    checkbox.addEventListener('change', () => { currentPage = 1; applyFilters(); });
    
    const text = document.createTextNode(labelText || value);
    item.appendChild(checkbox);
    item.appendChild(text);
    return item;
}

// Filter Logic
function applyFilters() {
    const keyword = keywordInput.value.toLowerCase().trim();
    
    // Get Checked Filters
    const checkedGenres = Array.from(document.querySelectorAll('input[data-filter-type="genre"]:checked')).map(el => el.value);
    const checkedSubgenres = Array.from(document.querySelectorAll('input[data-filter-type="subgenre"]:checked')).map(el => el.value);
    const checkedInstruments = Array.from(document.querySelectorAll('input[data-filter-type="instrument"]:checked')).map(el => el.value);
    const checkedProviders = Array.from(document.querySelectorAll('input[data-filter-type="provider"]:checked')).map(el => el.value);
    
    filteredData = scoresData.filter(item => {
        // Keyword Search (Title + Description)
        if (keyword) {
            const titleMatch = item.title && item.title.toLowerCase().includes(keyword);
            const descMatch = item.description && item.description.toLowerCase().includes(keyword);
            if (!titleMatch && !descMatch) return false;
        }
        
        // Genre & Subgenre (AND/OR Logic)
        // 大ジャンルがチェックされている、またはその大ジャンル内の特定のサブジャンルがチェックされている場合
        if (checkedGenres.length > 0) {
            // 資料の大ジャンルが選択されており、かつその大ジャンル内に選択されたサブジャンルがある場合、
            // そのサブジャンルがチェックされていれば合格。サブジャンル自体が未選択なら大ジャンル一致で合格。
            const hasParentSelected = checkedGenres.includes(item.genre);
            const associatedSubsSelected = checkedSubgenres.filter(sub => {
                const checkbox = document.querySelector(`input[value="${sub}"][data-filter-type="subgenre"]`);
                return checkbox && checkbox.dataset.parentGenre === item.genre;
            });
            
            if (associatedSubsSelected.length > 0) {
                // サブジャンルレベルでの絞り込みが走っている場合
                if (!checkedSubgenres.includes(item.subgenre)) {
                    return false;
                }
            } else if (!hasParentSelected) {
                // 大ジャンルも一致しない場合
                return false;
            }
        }
        
        // Instruments (AND Logic - 選択された全ての楽器を含む)
        if (checkedInstruments.length > 0) {
            if (!item.instruments || !Array.isArray(item.instruments)) return false;
            const hasAllInsts = checkedInstruments.every(inst => item.instruments.includes(inst));
            if (!hasAllInsts) return false;
        }
        
        // Provider
        if (checkedProviders.length > 0) {
            if (!checkedProviders.includes(item.provider)) return false;
        }
        
        return true;
    });

    // Sorting
    const sortVal = sortSelect.value;
    if (sortVal === 'title-asc') {
        filteredData.sort((a, b) => a.title.localeCompare(b.title, 'ja'));
    } else if (sortVal === 'title-desc') {
        filteredData.sort((a, b) => b.title.localeCompare(a.title, 'ja'));
    }

    matchCountEl.textContent = filteredData.length;
    renderGrid();
}

// Render Results Grid
function renderGrid() {
    cardsGrid.innerHTML = '';
    
    if (filteredData.length === 0) {
        cardsGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 60px; color: var(--text-secondary);">
            <h3>該当する資料が見つかりませんでした</h3>
            <p>検索キーワードや絞り込み条件を変更してお試しください。</p>
        </div>`;
        paginationContainer.innerHTML = '';
        return;
    }

    // Pagination slice
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, filteredData.length);
    const paginatedItems = filteredData.slice(startIndex, endIndex);

    paginatedItems.forEach(item => {
        const card = document.createElement('div');
        card.className = 'score-card';
        card.addEventListener('click', () => openModal(item));
        
        // Image Area
        const imgWrapper = document.createElement('div');
        imgWrapper.className = 'card-image-wrapper';
        if (item.image) {
            const img = document.createElement('img');
            img.src = item.image;
            img.alt = item.title;
            img.loading = 'lazy';
            imgWrapper.appendChild(img);
        } else {
            imgWrapper.innerHTML = placeholderSvg;
        }
        
        // Info Area
        const info = document.createElement('div');
        info.className = 'card-info';
        
        const provider = document.createElement('div');
        provider.className = 'card-provider';
        provider.textContent = item.provider === 'ADEAC' ? 'ADEAC' : '国立国会図書館';
        
        const title = document.createElement('h3');
        title.className = 'card-title';
        title.textContent = item.title;
        
        // Badges
        const badges = document.createElement('div');
        badges.className = 'card-badges';
        
        if (item.genre) {
            const gBadge = document.createElement('span');
            gBadge.className = 'badge badge-genre';
            gBadge.textContent = item.subgenre ? `${item.genre} (${item.subgenre})` : item.genre;
            badges.appendChild(gBadge);
        }
        
        if (Array.isArray(item.instruments)) {
            item.instruments.slice(0, 3).forEach(inst => {
                if (inst) {
                    const iBadge = document.createElement('span');
                    iBadge.className = 'badge badge-instrument';
                    iBadge.textContent = inst;
                    badges.appendChild(iBadge);
                }
            });
        }
        
        const desc = document.createElement('p');
        desc.className = 'card-description';
        desc.textContent = item.description || '詳細な説明はありません。';
        
        const footer = document.createElement('div');
        footer.className = 'card-footer';
        const viewBtn = document.createElement('span');
        viewBtn.className = 'btn btn-secondary';
        viewBtn.textContent = '詳細を見る';
        footer.appendChild(viewBtn);
        
        info.appendChild(provider);
        info.appendChild(title);
        info.appendChild(badges);
        info.appendChild(desc);
        info.appendChild(footer);
        
        card.appendChild(imgWrapper);
        card.appendChild(info);
        cardsGrid.appendChild(card);
    });

    renderPagination();
}

function renderPagination() {
    paginationContainer.innerHTML = '';
    const totalPages = Math.ceil(filteredData.length / itemsPerPage);
    if (totalPages <= 1) return;

    // Previous Button
    const prevBtn = document.createElement('button');
    prevBtn.className = `page-btn ${currentPage === 1 ? 'disabled' : ''}`;
    prevBtn.innerHTML = '&lt;';
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderGrid();
            window.scrollTo({ top: 300, behavior: 'smooth' });
        }
    });
    paginationContainer.appendChild(prevBtn);

    // Number Buttons
    // 簡易ページネーション (常に前後2ページと最初・最後を表示)
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);
    
    if (startPage > 1) {
        paginationContainer.appendChild(createPageNumBtn(1));
        if (startPage > 2) {
            const dots = document.createElement('span');
            dots.textContent = '...';
            dots.style.margin = '0 5px';
            paginationContainer.appendChild(dots);
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationContainer.appendChild(createPageNumBtn(i));
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const dots = document.createElement('span');
            dots.textContent = '...';
            dots.style.margin = '0 5px';
            paginationContainer.appendChild(dots);
        }
        paginationContainer.appendChild(createPageNumBtn(totalPages));
    }

    // Next Button
    const nextBtn = document.createElement('button');
    nextBtn.className = `page-btn ${currentPage === totalPages ? 'disabled' : ''}`;
    nextBtn.innerHTML = '&gt;';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderGrid();
            window.scrollTo({ top: 300, behavior: 'smooth' });
        }
    });
    paginationContainer.appendChild(nextBtn);
}

function createPageNumBtn(num) {
    const btn = document.createElement('button');
    btn.className = `page-btn ${num === currentPage ? 'active' : ''}`;
    btn.textContent = num;
    btn.addEventListener('click', () => {
        currentPage = num;
        renderGrid();
        window.scrollTo({ top: 300, behavior: 'smooth' });
    });
    return btn;
}

// Reset Filters
function resetFilters() {
    keywordInput.value = '';
    sortSelect.value = 'title-asc';
    
    // Uncheck all inputs
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
    
    // Close all genre accordions
    const accordionItems = document.querySelectorAll('.genre-accordion-item');
    accordionItems.forEach(item => {
        item.classList.remove('active');
        const icon = item.querySelector('.genre-accordion-toggle-icon');
        if (icon) icon.textContent = '▶';
        const content = item.querySelector('.genre-accordion-content');
        if (content) content.style.maxHeight = null;
    });

    currentPage = 1;
    applyFilters();
}

// Modal Control
function openModal(item) {
    modalTitle.textContent = item.title;
    modalDescription.textContent = item.description || '説明文はありません。';
    modalProvider.textContent = item.provider === 'ADEAC' ? 'ADEAC (地域特化型アーカイブ)' : '国立国会図書館 (NDLサーチ)';
    
    // Badges in Modal
    modalBadges.innerHTML = '';
    if (item.genre) {
        const gBadge = document.createElement('span');
        gBadge.className = 'badge badge-genre';
        gBadge.textContent = item.subgenre ? `ジャンル: ${item.genre} (${item.subgenre})` : `ジャンル: ${item.genre}`;
        modalBadges.appendChild(gBadge);
    }
    if (Array.isArray(item.instruments)) {
        item.instruments.forEach(inst => {
            if (inst) {
                const iBadge = document.createElement('span');
                iBadge.className = 'badge badge-instrument';
                iBadge.textContent = inst;
                modalBadges.appendChild(iBadge);
            }
        });
    }
    
    // Modal Image
    modalImageContainer.innerHTML = '';
    if (item.image) {
        const img = document.createElement('img');
        img.src = item.image;
        img.alt = item.title;
        modalImageContainer.appendChild(img);
    } else {
        const holder = document.createElement('div');
        holder.className = 'modal-placeholder';
        holder.innerHTML = placeholderSvg;
        modalImageContainer.appendChild(holder);
    }

    // Actions
    if (item.url && item.url !== item.id) {
        btnLinkOriginal.href = item.url;
        btnLinkOriginal.style.display = 'inline-flex';
    } else {
        btnLinkOriginal.style.display = 'none';
    }
    
    btnLinkJpSearch.href = item.id;
    
    // Show Modal
    detailModal.classList.remove('hide');
    document.body.style.overflow = 'hidden'; // prevent background scrolling
}

function closeModal() {
    detailModal.classList.add('hide');
    document.body.style.overflow = '';
}
"""

    # ファイル書き込み
    with open(f"{export_dir}/index.html", 'w', encoding='utf-8') as f:
        f.write(html_content)
    with open(f"{export_dir}/style.css", 'w', encoding='utf-8') as f:
        f.write(css_content)
    with open(f"{export_dir}/search.js", 'w', encoding='utf-8') as f:
        f.write(js_content)
    return True

