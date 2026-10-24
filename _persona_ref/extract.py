import re, html, os
from html.parser import HTMLParser

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
        self.in_script = 0
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("script","style"):
            self.in_script += 1
        if tag in ("p","div","li","h1","h2","h3","h4","br","tr","dt","dd","table"):
            self.parts.append("\n")
        if tag in ("td","th"):
            self.parts.append(" | ")
    def handle_endtag(self, tag):
        if tag in ("script","style"):
            self.in_script = max(0, self.in_script-1)
        if tag in ("p","div","li","h1","h2","h3","h4","dt","dd"):
            self.parts.append("\n")
    def handle_data(self, data):
        if self.in_script == 0:
            self.parts.append(data)

def extract(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    # narrow to main content for moegirl
    if "mw-parser-output" in raw:
        m = re.search(r'<div class="mw-parser-output">(.*?)<div class="printfooter"', raw, re.S)
        if m:
            raw = m.group(1)
    elif 'lemmaWap' in raw or 'lemma-summary' in raw:
        pass
    p = TextExtractor()
    p.feed(raw)
    text = "".join(p.parts)
    text = re.sub(r'[ \t\u3000]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text

for name in ["moegirl_maya_c", "moegirl_hc1_c", "wapbaike_maya"]:
    text = extract(os.path.join("_persona_ref", name + ".txt"))
    out = os.path.join("_persona_ref", name + ".txt2")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(name, "->", len(text), "chars")
