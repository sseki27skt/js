import json
import re
import os
import pandas as pd
from collections import Counter

# Configuration
INPUT_FILE = '/Users/shint/Desktop/JS_metadata/data/classical_scores_dynamic.jsonl'
OUTPUT_FILE = '/Users/shint/Desktop/JS_metadata/data/vocab_ranking_scores.csv'
TOP_N = 100

def extract_fu_compounds(text):
    """
    Extract words ending in '譜' from text.
    Matches Kanji and Katakana sequences ending in 譜.
    """
    if not isinstance(text, str):
        return []
    # Pattern: One or more Kanji/Katakana characters followed by '譜'
    matches = re.findall(r'([一-龠々ァ-ヶー]+譜)', text)
    return matches

def is_musical_score(record):
    """
    Check if the record represents a musical score.
    """
    # Check schema:about for the specific keyword URL
    about = record.get('schema:about')
    if about == 'https://jpsearch.go.jp/term/keyword/楽譜':
        return True
    
    # Check schema:description for "楽譜"
    description = record.get('schema:description')
    if description:
        if isinstance(description, list):
            for desc in description:
                if isinstance(desc, str) and '楽譜' in desc:
                    return True
        elif isinstance(description, str):
            if '楽譜' in description:
                return True
                
    return False

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"File not found: {INPUT_FILE}")
        return

    print(f"Processing {INPUT_FILE}...")
    
    all_compounds = []
    processed_count = 0
    match_count = 0
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                processed_count += 1
                if not line.strip():
                    continue
                
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                if is_musical_score(record):
                    match_count += 1
                    # Extract title
                    title = record.get('rdfs:label')
                    if not title:
                        title = record.get('schema:name')
                    
                    if isinstance(title, list):
                         title = title[0] if title else ""
                    
                    if title:
                        compounds = extract_fu_compounds(str(title))
                        all_compounds.extend(compounds)
                        
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print(f"Processed {processed_count} lines.")
    print(f"Found {match_count} records matching score criteria.")
    print(f"Extracted {len(all_compounds)} compounds ending in '譜'.")

    # Aggregation
    counter = Counter(all_compounds)
    
    print(f"\n=== Top {TOP_N} '〇〇譜' Compounds ===")
    print(f"{'Rank':<5} | {'Word':<20} | {'Count':<5}")
    print("-" * 40)
    
    rank = 1
    for word, count in counter.most_common(TOP_N):
        display_word = (word[:15] + '..') if len(word) > 15 else word
        print(f"{rank:<5} | {display_word:<20} | {count:<5}")
        rank += 1

    # Save to CSV
    df = pd.DataFrame(counter.most_common(), columns=['Word', 'Count'])
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"\nSaved ranking to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
