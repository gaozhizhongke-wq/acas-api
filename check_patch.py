import os, re

pat = re.compile(r"patch\(['\"](api|core|ml|sentiment)\.")
found = []
for dp, _, fns in os.walk("tests"):
    for fn in fns:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(dp, fn)
        for i, l in enumerate(open(p, encoding="utf-8"), 1):
            if pat.search(l):
                # skip if already src.-prefixed in the same token
                m = pat.search(l)
                before = l[: m.start()]
                if "src." in before[-12:]:
                    continue
                found.append("%s:%d: %s" % (p, i, l.strip()))

print("bare patch targets found:", len(found))
for x in found[:40]:
    print(x)
