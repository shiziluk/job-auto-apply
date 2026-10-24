import urllib.request, ssl, os
ctx = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
targets = [
    ("baike_maya", "https://baike.baidu.com/item/%E9%B8%A8%E5%B4%8E%E6%91%A9%E8%80%B6"),
    ("moegirl_hc1", "https://zh.moegirl.org.cn/api.php?action=parse&page=%E5%88%9D%E6%81%8B1%2F1&format=json&prop=wikitext"),
    ("moegirl_maya", "https://zh.moegirl.org.cn/api.php?action=parse&page=%E9%B4%87%E5%B4%8E%E6%91%A9%E8%80%B6&format=json&prop=wikitext"),
]
for name, u in targets:
    try:
        req = urllib.request.Request(u, headers={**UA, "Accept": "text/html,application/json"})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            data = resp.read()
        with open(os.path.join("_persona_ref", name + ".txt"), "wb") as f:
            f.write(data)
        print(name, "OK", len(data))
    except Exception as e:
        print(name, "ERR", repr(e))
