import json, re
with open("_persona_ref/baike_api_hc1.txt", "r", encoding="utf-8") as f:
    data = json.load(f)
print("KEY:", data.get("key"), "| TITLE:", data.get("title"))
print("DESC:", data.get("desc"))
ab = data.get("abstract", "")
# print abstract in chunks with unicode escapes decoded
print("ABSTRACT:", ab)
print()
for c in data.get("card", []):
    print(c.get("name"), "=>", c.get("value"))
