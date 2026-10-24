import urllib.request, ssl, re, os
ctx = ssl.create_default_context()
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
for name, u in [
    ("official", "http://www.toneworks.product.co.jp/hatsukoi1to1/"),
    ("official2", "https://toneworks.product.co.jp/hatsukoi1to1/"),
]:
    try:
        req = urllib.request.Request(u, headers=HDRS)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = resp.read()
        print(name, "OK", len(data))
        with open(os.path.join("_persona_ref", name + ".html"), "wb") as f:
            f.write(data)
    except Exception as e:
        print(name, "ERR", repr(e))
