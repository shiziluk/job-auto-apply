import urllib.request, ssl, os, http.cookiejar, urllib.parse
ctx = ssl.create_default_context()
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://baike.baidu.com/",
}
def fetch(name, url, headers=None, cookiejar=None, timeout=25):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar)) if cookiejar else urllib.request.build_opener()
    req = urllib.request.Request(url, headers=headers or HDRS)
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
        with open(os.path.join("_persona_ref", name + ".txt"), "wb") as f:
            f.write(data)
        print(name, "OK", len(data))
    except Exception as e:
        print(name, "ERR", repr(e))

cj = http.cookiejar.CookieJar()
# seed cookies via baidu homepage
fetch("baike_maya2", "https://baike.baidu.com/item/%E9%B8%A8%E5%B4%8E%E6%91%A9%E8%80%B6", cookiejar=cj)
fetch("baike_api", "https://baike.baidu.com/api/openapi/BaikeLemmaCardApi?scope=103&format=json&appid=379020&bk_key=%E9%B8%A8%E5%B4%8E%E6%91%A9%E8%80%B6")
fetch("moegirl_maya_wb", "https://web.archive.org/web/2024/https://zh.moegirl.org.cn/%E9%B4%87%E5%B4%8E%E6%91%A9%E8%80%B6")
fetch("moegirl_hc1_wb", "https://web.archive.org/web/2024/https://zh.moegirl.org.cn/%E5%88%9D%E6%81%8B1/1")
fetch("jawiki_hc1", "https://ja.wikipedia.org/wiki/%E5%88%9D%E6%81%8B1/1")
fetch("zhwiki_hc1", "https://zh.wikipedia.org/wiki/%E5%88%9D%E6%81%8B1/1")
