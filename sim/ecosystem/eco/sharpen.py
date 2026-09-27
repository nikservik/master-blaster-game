"""Пересчёт E1 с заострением: p' ∝ p^alpha (alpha = 2.35 снимает температуру сервера)."""
import json, math, sys
from pathlib import Path
from eco.formats import entropy, js

rows = json.loads((Path(__file__).resolve().parents[2] / "out" / "e1.json").read_text())
for alpha in (1.0, 2.35, 4.0):
    print(f"alpha {alpha}")
    for r in rows:
        m = pe = en = jd = 0.0; n = 0
        for s in r["situations"]:
            vecs = []
            for who in ("bold", "timid"):
                d = s[who]; w = {k: v ** alpha for k, v in d.items()}; z = sum(w.values()); w = {k: v / z for k, v in w.items()}
                m += max(w, key=w.get) in s["expected"]; pe += sum(w.get(e, 0) for e in s["expected"]); en += entropy(list(w.values())); n += 1
                vecs.append([w[k] for k in d])
            jd += js(*vecs)
        print(f"  {r['state']:8s} {r['instructions']:5s} {r['criteria']:6s} match {m/n:.2f} p(exp) {pe/n:.2f} entropy {en/n:.2f} JS {jd/len(r['situations']):.4f}")
