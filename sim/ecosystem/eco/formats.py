"""E1: влияет ли формат запроса на резкость решений Kev. Явные ситуации с очевидным ответом в разных форматах.

Форматы — произведение трёх осей:
- state: yaml (плотно, числа) / phrases (короткие английские фразы) / labels (числа со словесными ярлыками);
- instructions вопроса: none / role;
- criteria: names (только имена) / desc (описания, как в симуляции) / cond (когда вариант уместен).
Для каждого формата: доля совпадений argmax с ожидаемым, средняя p(ожидаемого), средняя энтропия выбора и
JS между смелой и трусливой особью в одной ситуации. Запуск в WSL: uv run python -m eco.formats [--repeat 1].
"""
import argparse
import asyncio
import itertools
import json
import math
from pathlib import Path

import eco.species as S
from eco.kev import KevClient

OUT = Path(__file__).resolve().parents[2] / "out"

COND = {
    "rest": "rest: lie down in cover when tired or at night and nothing threatens",
    "graze": "graze: eat where you are when hungry and it is safe",
    "drink": "drink: go to water when thirsty and it is safe",
    "follow": "follow: stay with the group leader or mother when they move away",
    "flee": "flee: run away when a predator is close or approaching",
    "hide": "hide: freeze in dense cover when a predator is far and has not noticed you",
    "explore": "explore: wander around when rested, fed and safe",
    "hunt": "hunt: stalk and chase prey when hungry and prey is near",
    "scavenge": "scavenge: eat from a carcass when hungry and one is here",
    "patrol": "patrol: walk the pack territory when fed and rested",
    "ambush": "ambush: wait hidden for prey to come close",
}
ROLE = "You decide what this wild {name} does next, as a real animal would."

# Ситуации: вид, факты, ожидаемые паттерны (первый — главный). Факты общие для всех форматов.
SITUATIONS = [
    ("roe", dict(hunger=0.9, thirst=0.2, fatigue=0.2, time="day", food="lush grass here"), ["graze"]),
    ("roe", dict(hunger=0.3, thirst=0.2, fatigue=0.2, time="day", threat=("wolf", 10, "running toward you")), ["flee"]),
    ("roe", dict(hunger=0.2, thirst=0.95, fatigue=0.2, time="day", water=15), ["drink"]),
    ("roe", dict(hunger=0.1, thirst=0.1, fatigue=0.9, time="night", cover="dense cover here"), ["rest"]),
    ("roe", dict(hunger=0.3, thirst=0.2, fatigue=0.2, time="day", leader=(40, "walking away")), ["follow"]),
    ("roe", dict(hunger=0.3, thirst=0.2, fatigue=0.2, time="dusk", threat=("lynx", 70, "still, has not noticed you"),
                 cover="dense cover here"), ["hide", "flee"]),
    ("hare", dict(hunger=0.9, thirst=0.1, fatigue=0.2, time="dusk", food="clover here"), ["graze"]),
    ("hare", dict(hunger=0.4, thirst=0.2, fatigue=0.2, time="day", threat=("fox", 8, "running toward you")), ["flee"]),
    ("hare", dict(hunger=0.4, thirst=0.2, fatigue=0.2, time="day", threat=("fox", 60, "still, has not noticed you"),
                  cover="dense bushes here"), ["hide"]),
    ("wolf", dict(hunger=0.9, thirst=0.2, fatigue=0.2, time="dusk", prey=("roe deer", 40, "young, grazing")), ["hunt"]),
    ("wolf", dict(hunger=0.1, thirst=0.1, fatigue=0.8, time="night", cover="den here"), ["rest"]),
    ("wolf", dict(hunger=0.7, thirst=0.2, fatigue=0.3, time="day", carcass=20), ["scavenge"]),
    ("jay", dict(hunger=0.9, thirst=0.2, fatigue=0.2, time="day", food="acorns here"), ["graze"]),
    ("jay", dict(hunger=0.2, thirst=0.9, fatigue=0.2, time="day", water=20), ["drink"]),
]
CHARACTERS = {"bold": dict(boldness=0.9, vigilance=0.1), "timid": dict(boldness=0.1, vigilance=0.9)}


def label(name: str, v: float) -> str:
    if name in ("boldness", "vigilance"):
        return ["very low", "low", "medium", "high", "very high"][min(4, int(v * 5))]
    return ["none", "slight", "moderate", "strong", "extreme"][min(4, int(v * 5))]


def render(state_fmt: str, species: str, f: dict, ch: dict) -> str:
    name = S.SPECIES[S.K[species]]["name"]
    needs = {k: f[k] for k in ("hunger", "thirst", "fatigue")}
    if state_fmt == "phrases":
        words = {"hunger": ["not hungry", "a bit hungry", "hungry", "very hungry", "starving"],
                 "thirst": ["not thirsty", "a bit thirsty", "thirsty", "very thirsty", "desperately thirsty"],
                 "fatigue": ["fresh", "a bit tired", "tired", "very tired", "exhausted"]}
        L = [f"A wild {name}, {f['time']}.",
             "It is " + ", ".join(words[k][min(4, int(v * 5))] for k, v in needs.items()) + ".",
             f"It is {'very bold and careless' if ch['boldness'] > 0.5 else 'timid and very watchful'}."]
        if "threat" in f:
            t = f["threat"]; L.append(f"A {t[0]} is {t[1]} m away, {t[2]}.")
        else:
            L.append("No predators around.")
        if "food" in f: L.append(f"There is {f['food']}.")
        if "water" in f: L.append(f"Water is {f['water']} m away.")
        if "cover" in f: L.append(f"There is {f['cover']}.")
        if "leader" in f: L.append(f"Its group leader is {f['leader'][0]} m away, {f['leader'][1]}.")
        if "prey" in f: p = f["prey"]; L.append(f"A {p[0]} is {p[1]} m away, {p[2]}.")
        if "carcass" in f: L.append(f"There is a carcass here, {f['carcass']} kg of meat.")
        return " ".join(L)
    lab = state_fmt == "labels"
    def num(k, v): return f"{k} {v:.2f}" + (f" ({label(k, v)})" if lab else "")
    L = [f"species: {name}", ", ".join(num(k, v) for k, v in needs.items()),
         ", ".join(num(k, v) for k, v in ch.items()), f"time: {f['time']}"]
    if "threat" in f:
        t = f["threat"]; L.append(f"sees {t[0]}: {t[1]} m, {t[2]}")
    else:
        L.append("threats: none")
    if "food" in f: L.append(f"food: {f['food']}")
    if "water" in f: L.append(f"water: {f['water']} m")
    if "cover" in f: L.append(f"cover: {f['cover']}")
    if "leader" in f: L.append(f"group leader: {f['leader'][0]} m, {f['leader'][1]}")
    if "prey" in f: p = f["prey"]; L.append(f"prey: {p[0]} {p[1]} m, {p[2]}")
    if "carcass" in f: L.append(f"carcass here: {f['carcass']} kg")
    return "\n".join(L)


def criteria(crit_fmt: str, species: str) -> dict:
    base = S.pattern_choices(S.K[species])
    if crit_fmt == "names":
        return {k: None for k in base}
    if crit_fmt == "cond":
        return {k: COND.get(k, base[k]).split(": ", 1)[1] for k in base}
    return base


def entropy(p: list[float]) -> float:
    return -sum(x * math.log2(x) for x in p if x > 0)


def js(p: list[float], q: list[float]) -> float:
    m = [(a + b) / 2 for a, b in zip(p, q)]
    kl = lambda a, b: sum(x * math.log2(x / y) for x, y in zip(a, b) if x > 0)
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="e1")
    args = ap.parse_args()
    formats = list(itertools.product(["yaml", "phrases", "labels"], ["none", "role"], ["names", "desc", "cond"]))
    rows = []
    async with KevClient(concurrency=16) as client:
        for sf, instr, cf in formats:
            match = p_exp = ent = jsd = 0.0
            n = 0
            per = []
            for species, f, expected in SITUATIONS:
                name = S.SPECIES[S.K[species]]["name"]
                q = {"type": "choice", "criteria": criteria(cf, species)}
                if instr == "role":
                    q["instructions"] = ROLE.format(name=name)
                answers = await asyncio.gather(*(client.ask(render(sf, species, f, ch), {"pattern": q})
                                                 for ch in CHARACTERS.values()))
                dists = [a.probabilities["pattern"] for a in answers]
                keys = list(dists[0])
                vecs = [[d[k] for k in keys] for d in dists]
                for d, v in zip(dists, vecs):
                    top = max(d, key=d.get)
                    match += top in expected
                    p_exp += sum(d.get(e, 0) for e in expected)
                    ent += entropy(v)
                    n += 1
                jsd += js(*vecs)
                per.append({"species": species, "expected": expected, "bold": dists[0], "timid": dists[1]})
            k = len(SITUATIONS)
            rows.append({"state": sf, "instructions": instr, "criteria": cf, "match": match / n, "p_expected": p_exp / n,
                         "entropy_bits": ent / n, "js_bold_timid": jsd / k, "situations": per})
            print(f"{sf:8s} {instr:5s} {cf:6s} match {match / n:.2f}  p(exp) {p_exp / n:.2f}  "
                  f"entropy {ent / n:.2f}  JS {jsd / k:.4f}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.label}.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
