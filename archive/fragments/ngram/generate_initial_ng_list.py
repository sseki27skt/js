import pandas as pd
import os

# Define heuristic noise patterns (suffixes or substrings)
# These are derived from viewing 'data/suffix_analysis_extended.csv' and common knowledge of Japan Search metadata.
NOISE_KEYWORDS = [
    "系譜", "家譜", "世譜", "年譜", "歴譜", "皇譜", "神譜", # Genealogy / History
    "花譜", "竹譜", "蘭譜", "菊譜", "梅譜", "椿譜", "百合譜", "草木", "菌譜", "蕈譜", "桜譜", # Plants / Botany
    "画譜", "図譜", "絵譜", "印譜", "額譜", "香譜", # Visual Arts / Incense
    "碁譜", "将棋", "棋譜", # Games
    "詩譜", "歌譜", "句譜", # Poetry (Careful: 歌譜 might be internal structure of songs, but often poetry anthology. '歌曲' is music. We will check this.)
    "相撲", "武鑑", "役者", # Entertainment / Directory
    "目録", "解題", # Bibliography
    "名譜" # Name list
]

# Note: "歌譜" is tricky. Some "歌譜" are song books (music), some are poetry.
# Given 'ng_word_list.txt' was empty, we'll start with a conservative list but include clear non-musical ones.
# "歌譜" appears in Rank 31 (40 counts) and likely includes music. So REMOVING it from the default noise list for now.
# "香譜" (Incense) is clear noise for music.
# "名譜" (Name list) is likely noise.

SAFE_KEYWORDS = ["楽譜", "琴譜", "笛譜", "三味線", "浄瑠璃", "謡本", "尺八", "工尺", "仮名譜", "歌譜"]

def generate_ng_list():
    input_csv = "data/suffix_analysis_extended.csv"
    output_file = "fragments/ngram/ng_word_list_final.txt"
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    df = pd.read_csv(input_csv)
    
    # Collect all unique words from Last2 to Last9 columns
    candidates = set()
    cols = [c for c in df.columns if "Last" in c]
    for col in cols:
        for val in df[col].dropna():
            # Value format: "Word (Count)"
            if "(" in str(val):
                word = str(val).split(" (")[0]
                candidates.add(word)

    # Filter
    final_ng = set()
    for word in candidates:
        # Check against noise keywords
        is_noise = False
        matching_noise = ""
        for noise in NOISE_KEYWORDS:
            if noise in word:
                is_noise = True
                matching_noise = noise
                break
        
        # Double check: if it contains a SAFE keyword, it might be a false positive? 
        # e.g. "雅楽系譜" (Genealogy of Gagaku performers) -> Still Genealogy, not Score.
        # But "仮名譜" (Kana Score) contains "名譜" (Name List) -> FALSE POSITIVE.
        
        if is_noise:
            # SAFETY CHECK
            is_safe = False
            for safe in SAFE_KEYWORDS:
                if safe in word:
                    # Special handling: "系譜" overrides "楽譜" (e.g. 楽譜系譜 -> Genealogy of scores? Unlikely)
                    # But "名譜" (Name List) vs "仮名譜" (Kana Score) -> Safe wins.
                    if matching_noise == "名譜" and "仮名譜" in word:
                        is_safe = True
                    elif matching_noise == "歌譜" and "歌譜" in word: # If we decide 歌譜 is safe
                         is_safe = True
                    
                    # Generically, if the word IS a safe word, keep it safe
                    if word == safe:
                        is_safe = True

            if not is_safe:
                final_ng.add(word)

    # Manual additions from previous context if any (only '系譜' was found)
    final_ng.add("系図")
    final_ng.add("系譜")

    # Sort and Save
    sorted_ng = sorted(list(final_ng))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for w in sorted_ng:
            f.write(w + "\n")
            
    print(f"Generated {len(sorted_ng)} NG words.")
    print(f"Saved to {output_file}")
    
    # Preview
    print("Top 10 NG words:", sorted_ng[:10])

if __name__ == "__main__":
    generate_ng_list()
