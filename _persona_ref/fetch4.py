import urllib.request, ssl, os, http.cookiejar
ctx = ssl.create_default_context()
BASE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
def fetch(name, url, headers=None, cookiejar=None, timeout=25):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar)) if cookiejar else urllib.request.build_opener()
    req = urllib.request.Request(url, headers=headers or BASE)
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
        with open(os.path.join("_persona_ref", name + ".txt"), "wb") as f:
            f.write(data)
        print(name, "OK", len(data))
    except Exception as e:
        print(name, "ERR", repr(e))

fetch("wapbaike_maya", "http://wapbaike.baidu.com/item/%E9%B8%A8%E5%B4%8E%E6%91%A9%E8%80%B6")
fetch("baike_wapapi", "https://baike.baidu.com/wapapi/lemmaparse/24591671")
cj = http.cookiejar.CookieJar()
fetch("moegirl_home", "https://zh.moegirl.org.cn/", cookiejar=cj)
fetch("moegirl_maya_c", "https://zh.moegirl.org.cn/%E9%B4%87%E5%B4%8E%E6%91%A9%E8%80%B6", cookiejar=cj)
fetch("moegirl_hc1_c", "https://zh.moegirl.org.cn/%E5%88%9D%E6%81%8B1/1", cookiejar=cj)
