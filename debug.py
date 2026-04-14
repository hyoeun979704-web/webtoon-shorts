import re
import pprint

with open('temp/last_keyword_response.txt', 'r', encoding='utf-8') as f:
    text = f.read()

_NUM_ID = r"[가-힣A-Za-z]+[\s]*-[\s]*\d+"
_HEADER_PATTERNS = [
    re.compile(rf"\[({_NUM_ID})\]\s*(.*)"),
    re.compile(rf"[◆◇●○▶►★☆🔷🔶📌📍🏷️💡✅❇️#※]\s*({_NUM_ID})\s*(.*)"),
    re.compile(rf"\*\*({_NUM_ID})\*\*\s*(.*)"),
    re.compile(rf"#{1,4}\s*({_NUM_ID})\s*(.*)"),
]

def _match_header(line: str):
    for pat in _HEADER_PATTERNS:
        m = pat.search(line)
        if m:
            num = re.sub(r"\s+", "", m.group(1))
            title = m.group(2).strip() if m.group(2) else ""
            if "글자" in num or "채점" in num:
                return None
            return num, title
    return None

items = []
seen_numbers = set()
current_item = None

for line in text.split("\n"):
    line = line.strip()
    if not line:
        continue
    
    header = _match_header(line)
    if header:
        number, title = header
        print("HEADER MATCH:", number, title)
        if number in seen_numbers: continue
        seen_numbers.add(number)
        current_item = {
            "number": number,
            "title": title,
            "keywords": [],
            "cta": "",
        }
        items.append(current_item)
        print("NEW ITEM ADDED.")
        continue

    if current_item:
        print("TRYING TO MATCH IN ITEM:", line)
        kw_match = re.match(r"키워드\s*[:：]\s*(.+)", line)
        if kw_match:
            print("  -> KW MATCH!", kw_match.group(1))
            kw_str = kw_match.group(1).strip()
            current_item["keywords"] = [k.strip() for k in kw_str.split(",") if k.strip()]
            if not current_item["title"] and current_item["keywords"]:
                current_item["title"] = current_item["keywords"][0]
            continue
            
        cta_match = re.match(r"CTA\s*유형\s*[:：]\s*(.+)", line)
        if cta_match:
            print("  -> CTA MATCH!", cta_match.group(1))
            current_item["cta"] = cta_match.group(1).strip()
            continue

pprint.pprint(items)
