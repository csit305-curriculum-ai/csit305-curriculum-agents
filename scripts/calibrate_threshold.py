"""Calibrate the coverage-gate similarity threshold (DEC 008).
In-scope queries paraphrase Grade 3-4 curriculum topics; out-of-scope queries are off-curriculum or wrong-level."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cagents.retrieval import BGEM3Embedder, Index, ROOT

IN = [("maths", 3, "place value of whole numbers through thousands"), ("maths", 3, "multiplication facts and arrays"),
      ("maths", 3, "understanding fractions as equal parts of a whole"), ("maths", 3, "telling time and elapsed time"),
      ("maths", 3, "area and perimeter of rectangles"), ("maths", 4, "multiplying two-digit numbers"),
      ("maths", 4, "equivalent fractions and comparing fractions"), ("maths", 4, "decimals tenths and hundredths"),
      ("maths", 4, "measuring angles"), ("maths", 4, "factors and multiples"),
      ("science", 3, "states of matter solids liquids and gases"), ("science", 4, "the water cycle and Earth's systems"),
      ("science", 3, "plants and animals life cycles"), ("science", 4, "forces and motion of objects"),
      ("science", 4, "energy sources and transfer")]
OUT = [("maths", 3, "the causes of the French Revolution"), ("maths", 4, "derivatives and integrals in calculus"),
       ("maths", 3, "quadratic equations and the discriminant"), ("maths", 4, "persuasive essay writing techniques"),
       ("maths", 3, "football match tactics"), ("science", 3, "Shakespeare's sonnets"),
       ("science", 4, "stock market investment strategy"), ("science", 3, "Arabic grammar rules for verbs"),
       ("science", 4, "quantum chromodynamics and quark confinement"), ("science", 3, "how to cook biryani"),
       ("maths", 4, "trigonometric identities"), ("science", 4, "organic chemistry reaction mechanisms")]

idx = Index(BGEM3Embedder())
def top(s, g, q):
    b = idx.retrieve(q, s, g, threshold=-1.0)
    return b.chunks[0]["score"] if b.chunks else None
res = {"in_scope": [(s, g, q, top(s, g, q)) for s, g, q in IN], "out_of_scope": [(s, g, q, top(s, g, q)) for s, g, q in OUT]}
ins = [r[3] for r in res["in_scope"]]; outs = [r[3] for r in res["out_of_scope"]]
res["summary"] = {"in_min": min(ins), "in_mean": sum(ins)/len(ins), "out_max": max(outs), "out_mean": sum(outs)/len(outs)}
(ROOT / "corpus" / "processed" / "calibration.json").write_text(json.dumps(res, indent=1))
for k in ("in_scope", "out_of_scope"):
    for r in res[k]: print(k, r)
print(res["summary"])
