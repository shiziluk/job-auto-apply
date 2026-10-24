import urllib.request, ssl, os, json, urllib.parse
ctx = ssl.create_default_context()
HDRS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
def fetch(name, url, timeout=25):
    req = urllib.request.Request(url, headers=HDRS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = resp.read()
        with open(os.path.join("_persona_ref", name + ".txt"), "wb") as f:
            f.write(data)
        print(name, "OK", len(data))
    except Exception as e:
        print(name, "ERR", repr(e))

key = urllib.parse.quote("初恋1/1")
fetch("baike_api_hc1", "https://baike.baidu.com/api/openapi/BaikeLemmaCardApi?scope=103&format=json&appid=379020&bk_key=" + key)
fetch("wapbaike_hc1", "http://wapbaike.baidu.com/item/" + key)
