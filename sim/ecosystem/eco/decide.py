"""Решатели и асинхронный драйвер решений.

Запрос решения — (особь, вид запроса: паттерн или реакция). Решатель отвечает сразу (Random, V0, попадание в кэш,
личная политика) или отправляет вопрос оракулу (Kev или Mock). Пока ответ не пришёл, особь держит прежний паттерн.
Выбор всегда семплируется из распределения.
"""
import asyncio
import math
import re
import time
from dataclasses import dataclass, field

import numpy as np

from eco import species as S
from eco.kev import Answer, KevClient
from eco.sim import EV_ALARM, EV_GROUP, EV_PREY, EV_THREAT, EVENTS, KIND_PATTERN, KIND_REACTION, PHYS, TRAITS, Sim
from eco.species import P

NP = len(S.PATTERNS)
COMMIT = [P["graze"], P["drink"], P["rest"], P["scavenge"], P["hunt"]]
PREY_OPTS = list(S.REACTIONS_PREY)          # continue, freeze, flee, investigate
PRED_OPTS = list(S.REACTIONS_PRED)          # continue, stalk, investigate
COMPASS = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
# Роль у вопросов паттерна и реакции (E1): с ней распределения резче и характеры различаются сильнее.
ROLE = "You decide what this wild {name} does next, as a real animal would."


def role(s: int) -> str:
    return ROLE.format(name=S.SPECIES[s]["name"])


Q_ALARM = "Should the animal call an alarm to warn others right now?"
Q_JOIN = "Should the animal join the nearby animals of its kind as a group?"
Q_CHAL = "Should the animal challenge the group leader for leadership now?"


@dataclass
class Batch:
    """Решения, готовые к применению (массивы одной длины)."""
    idx: np.ndarray
    uid: np.ndarray
    kind: np.ndarray
    pattern: np.ndarray          # -1 — продолжать
    target: np.ndarray
    alarm: np.ndarray
    join: np.ndarray
    challenge: np.ndarray
    pmat: np.ndarray             # (n, NP) распределение по паттернам для запросов паттерна, NaN для реакций
    source: list[str]
    detail: list[dict] | None = None

    @staticmethod
    def empty(n: int = 0) -> "Batch":
        return Batch(np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.full(n, -1), np.full(n, -1),
                     np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool), np.full((n, NP), np.nan), [""] * n, None)

    @staticmethod
    def concat(bs: list["Batch"]) -> "Batch":
        bs = [b for b in bs if len(b.idx)]
        if not bs:
            return Batch.empty()
        det = None
        if any(b.detail is not None for b in bs):
            det = sum((b.detail or [None] * len(b.idx) for b in bs), [])
        return Batch(*(np.concatenate([getattr(b, f) for b in bs]) for f in
                       ("idx", "uid", "kind", "pattern", "target", "alarm", "join", "challenge", "pmat")),
                     sum((b.source for b in bs), []), det)


def softmax(x: np.ndarray, temp: float) -> np.ndarray:
    z = x / temp
    z = z - np.max(z, axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


def sample_rows(rng: np.random.Generator, p: np.ndarray) -> np.ndarray:
    c = np.cumsum(p, 1)
    return np.minimum((c < rng.random((len(p), 1)) * c[:, -1:]).sum(1), p.shape[1] - 1)


# ---------------------------------------------------------------------- признаки и V0
def features(sim: Sim, idx: np.ndarray) -> dict:
    sp = sim.sp[idx]
    tr = sim.traits[idx]
    lead = sim._lead[idx]
    thr = sim.thr[idx]
    light = sim.light()
    yd = sim.year_days
    grp = sim.grp[idx]
    leader = (grp >= 0) & (sim.g_leader[np.maximum(grp, 0)] == idx) if len(sim.g_leader) else np.zeros(len(idx), bool)
    return dict(sp=sp, h=sim.hunger[idx], th=sim.thirst[idx], fa=sim.fatigue[idx], hp=sim.health[idx],
                bold=tr[:, 0], cur=tr[:, 1], soc=tr[:, 2], dom=tr[:, 3], vig=tr[:, 4],
                threat=thr >= 0, near=(thr >= 0) & (sim.thr_d[idx] < 30), lead=lead, has_lead=lead >= 0,
                leader=leader, member=(grp >= 0) & ~leader, night=np.full(len(idx), light < 0.2),
                juv=sim.age[idx] < S.MATURITY[sp] * yd, prey_vis=sim.prey[idx, 0] >= 0,
                alarm=(sim.t - sim.ev_t[idx, EV_ALARM] < 5) | (sim.t - sim.ev_t[idx, EV_GROUP] < 5),
                solo_near=(grp < 0) & S.SOCIAL[sp] & (sim.cons[idx] >= 0) & (sim.cons_d[idx] < 30),
                carcass=sim.world.carrion[sim.world.cell(sim.pos[idx])] > 0.05,
                pattern=sim.pattern[idx].astype(np.int64), done=sim.done[idx])


def v0_pattern_scores(f: dict) -> np.ndarray:
    sp, h, th, fa = f["sp"], f["h"], f["th"], f["fa"]
    n = len(sp)
    diurnal = S.NIGHT[sp] < 0.5
    nocturnal = S.NIGHT[sp] >= 1.0
    sc = np.full((n, NP), -9.0)
    sc[:, P["rest"]] = 1.2 * fa + 0.6 * (f["night"] & diurnal) + 0.4 * (~f["night"] & nocturnal) - 0.3 * h - 0.3 * th
    sc[:, P["graze"]] = 1.3 * h + 0.05
    sc[:, P["drink"]] = 1.4 * th
    raven = sp == S.K["raven"]
    sc[:, P["follow"]] = np.where(f["has_lead"], np.where(raven, 0.2 + 0.6 * h, 0.35 + 0.5 * f["soc"] + 0.6 * f["juv"] - 0.6 * np.maximum(h, th)), -5)
    sc[:, P["flee"]] = f["near"] * (1.5 - 0.8 * f["bold"]) + f["threat"] * 0.3 - 0.2
    sc[:, P["hide"]] = f["threat"] * (0.7 - 0.4 * f["bold"]) + (sp == S.K["hare"]) * f["threat"] * 0.3 - 0.1
    sc[:, P["explore"]] = 0.15 + 0.3 * f["cur"]
    sc[:, P["hunt"]] = np.where(f["prey_vis"], 3.0 * (h - 0.4) + 0.4, 1.5 * (h - 0.5)) - 0.4 * fa
    sc[:, P["scavenge"]] = h * (0.6 + S.DIET[sp, 4]) - 0.2 + f["carcass"] * S.DIET[sp, 4] * (0.6 + 2 * h)
    sc[:, P["patrol"]] = 0.4 * f["leader"]
    sc[:, P["ambush"]] = 3.0 * (h - 0.4) + 0.3
    keep = f["pattern"]   # приверженность начатому: занятие, которое ещё не закончено, получает надбавку
    sc[np.arange(len(sp)), keep] += np.where(np.isin(keep, COMMIT) & ~f["done"], 0.3, 0.0)
    sc[~S.ALLOWED[sp]] = -np.inf
    sc[:, P["investigate"]] = -np.inf
    return sc


def v0_reaction_scores(f: dict) -> tuple[np.ndarray, np.ndarray]:
    near, thr, al = f["near"], f["threat"], f["alarm"]
    prey = np.stack([0.5 + 0.4 * f["bold"] - 1.2 * near - 0.4 * thr,
                     0.3 + 0.4 * f["vig"] * (thr | al) + 0.3 * (f["sp"] == S.K["hare"]),
                     near * (1.4 - 0.6 * f["bold"]) + 0.3 * thr + al * (0.5 - 0.4 * f["bold"]),
                     0.6 * f["cur"] * f["bold"] - near - 0.1], 1)
    pred = np.stack([0.4 - 0.5 * f["h"] + 0.3 * f["fa"],
                     np.where(f["prey_vis"], 2.5 * (f["h"] - 0.4) + 0.2 * f["bold"] + 0.3, -np.inf),
                     0.2 * f["cur"] + 0.0 * f["h"]], 1)
    return prey, pred


def v0_target(sim: Sim, idx: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Цель хищника: уязвимость (детёныш, слабое здоровье, усталость) против дистанции; семпл."""
    pr = sim.prey[idx]
    ok = pr >= 0
    q = np.maximum(pr, 0)
    juv = sim.age[q] < S.MATURITY[sim.sp[q]] * sim.year_days
    sc = 0.8 * juv + (1 - sim.health[q]) + 0.5 * (1 - sim.stamina[q]) - sim.prey_d[idx] / 30
    sc = np.where(ok, sc, -np.inf)
    out = np.full(len(idx), -1)
    has = ok.any(1)
    if has.any():
        k = sample_rows(rng, softmax(sc[has], 0.2))
        out[has] = pr[has][np.arange(has.sum()), k]
    return out


def reaction_to_pattern(names: np.ndarray, pred: np.ndarray) -> np.ndarray:
    out = np.full(len(names), -1)
    for name, p in S.REACTION_TO_PATTERN.items():
        out[names == name] = p
    return out


class Solver:
    """Синхронный решатель: decide() возвращает Batch сразу."""
    name = "solver"
    oracle = None
    want_detail = False

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed + 7)

    def handle(self, sim: Sim, idx: np.ndarray, kind: np.ndarray) -> tuple[Batch, list]:
        return self.decide(sim, idx, kind), []


class UtilitySolver(Solver):
    """V0 — ручной utility AI, векторно; температура — насколько выбор разбросан вокруг лучшего."""
    name = "V0"
    TEMP = 0.12

    def decide(self, sim: Sim, idx: np.ndarray, kind: np.ndarray, source: str = "v0") -> Batch:
        n = len(idx)
        b = Batch.empty(n)
        if not n:
            return b
        f = features(sim, idx)
        rng = self.rng
        b.idx, b.uid, b.kind = idx, sim.uid[idx], kind
        pm = kind == KIND_PATTERN
        probs = softmax(v0_pattern_scores({k: v[pm] for k, v in f.items()}), self.TEMP)
        b.pattern[pm] = sample_rows(rng, probs)
        b.pmat[pm] = probs
        rm = ~pm
        detail_r = {}
        if rm.any():
            fr = {k: v[rm] for k, v in f.items()}
            prey_s, pred_s = v0_reaction_scores(fr)
            is_pred = S.IS_PRED[fr["sp"]]
            names = np.empty(rm.sum(), object)
            pp, pd = softmax(prey_s, 0.15), softmax(pred_s, 0.15)
            names[~is_pred] = np.array(PREY_OPTS, object)[sample_rows(rng, pp[~is_pred])] if (~is_pred).any() else []
            names[is_pred] = np.array(PRED_OPTS, object)[sample_rows(rng, pd[is_pred])] if is_pred.any() else []
            b.pattern[rm] = reaction_to_pattern(names, is_pred)
            detail_r = dict(pp=pp, pd=pd, is_pred=is_pred)
        preds = S.IS_PRED[f["sp"]]
        b.target[preds] = v0_target(sim, idx[preds], rng)
        p_al = np.where(f["sp"] == S.K["jay"], 0.2 + 0.7 * f["vig"], np.where(f["member"] | f["leader"], 0.15 + 0.6 * f["vig"], 0))
        p_al = p_al * f["threat"] * ~pm
        p_join = np.where(f["solo_near"] & ~f["juv"] & pm, 0.8 * f["soc"], 0)
        p_ch = np.where(f["member"] & ~f["juv"] & pm, 0.03 * np.clip(f["dom"] - 0.6, 0, None) / 0.4, 0)
        b.alarm = rng.random(n) < p_al
        b.join = rng.random(n) < p_join
        b.challenge = rng.random(n) < p_ch
        b.source = [source] * n
        if self.want_detail:
            b.detail = []
            ri = pi = 0
            for j in range(n):
                d = {"src": source}
                if pm[j]:
                    d["pattern"] = {S.PATTERNS[k]: round(float(probs[pi, k]), 3) for k in range(NP) if probs[pi, k] > 0.001}
                    pi += 1
                else:
                    ip = detail_r["is_pred"][ri]
                    row = detail_r["pd" if ip else "pp"][ri]
                    d["reaction"] = {o: round(float(v), 3) for o, v in zip(PRED_OPTS if ip else PREY_OPTS, row)}
                    ri += 1
                if p_al[j] > 0:
                    d["alarm"] = round(float(p_al[j]), 3)
                b.detail.append(d)
        return b


class RandomSolver(Solver):
    """Нижняя граница: равномерный выбор из допустимого."""
    name = "random"

    def decide(self, sim: Sim, idx: np.ndarray, kind: np.ndarray) -> Batch:
        n = len(idx)
        b = Batch.empty(n)
        if not n:
            return b
        rng = self.rng
        sp = sim.sp[idx]
        b.idx, b.uid, b.kind = idx, sim.uid[idx], kind
        pm = kind == KIND_PATTERN
        allowed = S.ALLOWED[sp].astype(float)
        allowed[:, P["investigate"]] = 0
        probs = allowed / allowed.sum(1, keepdims=True)
        b.pattern[pm] = sample_rows(rng, probs[pm])
        b.pmat[pm] = probs[pm]
        is_pred = S.IS_PRED[sp]
        opts = np.where(is_pred, rng.integers(0, len(PRED_OPTS), n), rng.integers(0, len(PREY_OPTS), n))
        names = np.array([(PRED_OPTS if ip else PREY_OPTS)[o] for ip, o in zip(is_pred, opts)], object)
        b.pattern[~pm] = reaction_to_pattern(names[~pm], is_pred[~pm])
        pr = sim.prey[idx]
        k = rng.integers(0, 4, n)
        b.target = np.where(is_pred, pr[np.arange(n), k], -1)
        b.target = np.where(is_pred & (b.target < 0), pr[:, 0], b.target)
        b.alarm, b.join, b.challenge = rng.random(n) < 0.5, (rng.random(n) < 0.5) & pm, (rng.random(n) < 0.5) & pm
        b.source = ["random"] * n
        if self.want_detail:
            b.detail = [{"src": "random"} for _ in range(n)]
        return b


# ---------------------------------------------------------------------- state и вопросы для оракула
def bearing(v: np.ndarray) -> str:
    return COMPASS[int(round(math.atan2(v[1], v[0]) / (math.pi / 4))) % 8]


def _where(sim: Sim, i: int, p: np.ndarray) -> str:
    v = p - sim.pos[i]
    return f"{np.hypot(*v):.0f} m {bearing(v)}"


LEVEL = {"hunger": ["not hungry", "a bit hungry", "hungry", "very hungry", "starving"],
         "thirst": ["not thirsty", "a bit thirsty", "thirsty", "very thirsty", "desperately thirsty"],
         "fatigue": ["fresh", "a bit tired", "tired", "very tired", "exhausted"]}
# Черта характера или физики словами: (низкое, высокое); середина не упоминается.
TRAIT_WORDS = {"boldness": ("timid", "very bold"), "curiosity": ("incurious", "very curious"),
               "sociability": ("solitary", "very sociable"), "dominance": ("submissive", "dominant"),
               "vigilance": ("careless", "very watchful")}
PHYS_WORDS = {"speed": ("slow", "fast"), "stamina": ("tires quickly", "has great endurance"),
              "strength": ("weak", "strong"), "senses": ("has dull senses", "has sharp senses")}


def _level(name: str, v: float) -> str:
    return LEVEL[name][min(4, int(v * 5))]


def _traits(names, words, values) -> list[str]:
    return [words[n][0] if v < 0.3 else words[n][1] for n, v in zip(names, values) if v < 0.3 or v > 0.7]


def state_text(sim: Sim, i: int, kind: int) -> str:
    """State особи короткими английскими фразами, 100–300 токенов. Формат выбран в E1 (eco/formats.py): фразы
    дают Kev заметно более резкие распределения и различие характеров, чем плотный YAML с числами."""
    s = int(sim.sp[i]); sp = S.SPECIES[s]; yd = sim.year_days
    juv = sim.age[i] < S.MATURITY[s] * yd
    tr, ph = sim.traits[i], sim.phys[i]
    L = [f"A wild {sp['name']}, {'male' if sim.sex[i] else 'female'}, {sim.age[i] / yd:.1f} years old"
         f"{', young' if juv else ''}{', pregnant' if sim.pregnant[i] else ''}. "
         f"It is {sim.daypart()} in {S.SEASONS[sim.season()]}, "
         f"{'in dense forest' if sim.world.forest_at(sim.pos[i][None])[0] > 0.6 else 'in open woodland'}.",
         f"It is {_level('hunger', sim.hunger[i])}, {_level('thirst', sim.thirst[i])} and {_level('fatigue', sim.fatigue[i])}"
         f"{', wounded' if sim.health[i] < 0.5 else ''}{', out of breath' if sim.stamina[i] < 0.3 else ''}."]
    look = _traits(TRAITS, TRAIT_WORDS, tr) + _traits(PHYS, PHYS_WORDS, ph)
    if look:
        L.append(f"It is {', '.join(look)}.")
    L.append(f"It has been doing this for {sim.t - sim.pattern_t[i]:.0f} s: {S.PATTERNS[sim.pattern[i]]}.")
    g = sim.grp[i]
    lead = sim._lead[i]
    if g >= 0:
        n = int(sim._gs[i])
        if sim.g_leader[g] == i:
            L.append(f"It leads a group of {n}.")
        elif lead >= 0:
            L.append(f"It is in a group of {n}; the leader is {_where(sim, i, sim.pos[lead])} and doing: "
                     f"{S.PATTERNS[sim.pattern[lead]]}.")
        else:
            L.append(f"It is in a group of {n}.")
    elif lead >= 0 and s != S.K["raven"]:
        L.append(f"Its mother is {_where(sim, i, sim.pos[lead])}.")
    else:
        L.append("It is alone.")
    if s == S.K["raven"] and lead >= 0:
        L.append(f"The nearest wolf is {_where(sim, i, sim.pos[lead])}.")
    th = sim.thr[i]
    if th >= 0:
        mv = "running" if sim.spd[th] > 0.5 * S.RUN[sim.sp[th]] else ("moving" if sim.spd[th] > 0.2 else "still")
        how = ["", "seen", "heard", "smelled"][sim.thr_mode[i]]
        L.append(f"A {S.SPECIES[sim.sp[th]]['name']} is {_where(sim, i, sim.pos[th])}, {mv} ({how}).")
    elif not S.IS_PRED[s]:
        L.append("No predator in sight.")
    for k, (q, d) in enumerate(zip(sim.prey[i], sim.prey_d[i])):
        if q >= 0 and S.IS_PRED[s]:
            qj = sim.age[q] < S.MATURITY[sim.sp[q]] * yd
            L.append(f"Prey {k}: a {'young' if qj else 'adult'} {S.SPECIES[sim.sp[q]]['name']} {_where(sim, i, sim.pos[q])}"
                     f"{', weak' if sim.health[q] < 0.5 else ''}{', fleeing' if sim.act[q] == P['flee'] else ''}.")
    kg = sim.world.carrion[sim.world.cell(sim.pos[i][None])][0]
    if kg > 0.05:
        L.append(f"There is a carcass here, {kg:.1f} kg of meat.")
    if sim.cons[i] >= 0 and g < 0:
        L.append(f"Another {sp['name']} is {sim.cons_d[i]:.0f} m away.")
    if not np.isnan(sim.mem_water[i, 0]):
        L.append(f"Water is {_where(sim, i, sim.mem_water[i])}.")
    if sim.t - sim.mem_pred_t[i] < 120:
        L.append(f"It saw a predator {_where(sim, i, sim.mem_pred[i])} {sim.t - sim.mem_pred_t[i]:.0f} s ago.")
    for e in range(4):
        ago = sim.t - sim.ev_t[i, e]
        if ago < 5 and e != EV_PREY:
            L.append(f"Just now ({ago:.0f} s ago): {EVENTS[e]}, {_where(sim, i, sim.ev_src[i])}.")
    L.append("Question: " + ("what does it do now?" if kind == KIND_PATTERN else "how does it react to the event?"))
    return "\n".join(L)


def questions_for(sim: Sim, i: int, kind: int) -> tuple[dict, dict]:
    """Вопросы (2–4) и соответствие вариантов цели индексам добычи."""
    s = int(sim.sp[i])
    q = {}
    if kind == KIND_PATTERN:
        q["pattern"] = {"type": "choice", "criteria": S.pattern_choices(s), "instructions": role(s)}
    else:
        q["reaction"] = {"type": "choice", "criteria": S.reaction_choices(s), "instructions": role(s)}
    tmap = {}
    if S.IS_PRED[s] and sim.prey[i, 0] >= 0:
        crit = {}
        for k, (p, d) in enumerate(zip(sim.prey[i], sim.prey_d[i])):
            if p >= 0:
                qj = sim.age[p] < S.MATURITY[sim.sp[p]] * sim.year_days
                crit[f"prey_{k}"] = f"{S.SPECIES[sim.sp[p]]['name']} at {d:.0f} m, {'young' if qj else 'adult'}"
                tmap[f"prey_{k}"] = int(p)
        q["target"] = {"type": "choice", "criteria": crit}
    if sim.thr[i] >= 0 and (s == S.K["jay"] or sim.grp[i] >= 0):
        q["alarm"] = {"type": "noul", "instructions": Q_ALARM}
    if kind == KIND_PATTERN and len(q) < 4:
        grp = sim.grp[i]
        adult = sim.age[i] >= S.MATURITY[s] * sim.year_days
        if grp < 0 and S.SOCIAL[s] and sim.cons[i] >= 0 and sim.cons_d[i] < 30:
            q["join"] = {"type": "noul", "instructions": Q_JOIN}
        elif grp >= 0 and sim.g_leader[grp] != i and adult:
            q["challenge"] = {"type": "noul", "instructions": Q_CHAL}
    return q, tmap


def pick(rng: np.random.Generator, dist: dict[str, float]) -> str:
    names = list(dist)
    p = np.array([max(0.0, float(dist[n])) for n in names])
    if p.sum() <= 0:
        return names[int(rng.integers(len(names)))]
    return names[int(np.searchsorted(np.cumsum(p / p.sum()), rng.random() * 0.999999))]


# ---------------------------------------------------------------------- оракулы
class MockOracle:
    """Синтетический оракул: распределения из разобранного state, искусственная задержка.
    gate — asyncio.Event: пока не установлен, ответы не приходят (для тестов асинхронности)."""

    def __init__(self, latency_s: float = 0.0, seed: int = 0, gate: asyncio.Event | None = None, temp: float = 0.25):
        self.latency_s, self.gate, self.temp = latency_s, gate, temp
        self.rng = np.random.default_rng(seed + 11)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    @staticmethod
    def parse(state: str) -> dict:
        f = {k: float(v) for k, v in re.findall(r"([a-z]+) (-?[0-9]+\.[0-9]+)", state)}
        m = re.search(r"sees [a-z ]+: (\d+) m", state)
        f["threat_d"] = float(m.group(1)) if m else 1e9
        f["prey"] = float("prey_0" in state)
        f["night"] = float("time: night" in state)
        f["leader"] = float("leader " in state or "mother " in state or "nearest wolf" in state)
        f["alarm"] = float("event:" in state)
        f["carcass"] = float("carcass here" in state)
        return f

    def distributions(self, state: str, questions: dict) -> Answer:
        f = self.parse(state)
        g = lambda k: f.get(k, 0.0)
        near = float(g("threat_d") < 30); thr = float(g("threat_d") < 1e8)
        base = {"graze": 1.3 * g("hunger"), "drink": 1.4 * g("thirst"), "rest": 1.2 * g("fatigue") + 0.3 * g("night"),
                "flee": near * (1.5 - g("boldness")) + 0.3 * thr - 0.2, "hide": thr * 0.6 * (1 - g("boldness")),
                "explore": 0.2 + 0.3 * g("curiosity"), "follow": g("leader") * (0.3 + 0.5 * g("sociability")) - 0.3,
                "hunt": g("prey") * 1.3 * g("hunger"), "patrol": 0.3,
                "scavenge": 0.6 * g("hunger") + g("carcass") * (0.6 + 2 * g("hunger")),
                "investigate": 0.3 * g("curiosity"), "ambush": 0.9 * g("hunger"),
                "continue": 0.4 + 0.3 * g("boldness") - near, "freeze": 0.5 * g("vigilance"),
                "stalk": g("prey") * g("hunger")}
        base["flee"] += 0.4 * g("alarm") * (1 - g("boldness"))
        probs, noul = {}, {}
        for name, q in questions.items():
            if q["type"] == "choice":
                opts = list(q["criteria"])
                if name == "target":
                    d = np.array([float(re.search(r"(\d+) m", q["criteria"][o]).group(1)) for o in opts])
                    sc = -d / 15
                else:
                    sc = np.array([base.get(o, 0.0) for o in opts])
                p = softmax(sc, self.temp)
                probs[name] = {o: float(v) for o, v in zip(opts, p)}
            else:
                noul[name] = float(np.clip({"alarm": 0.2 + 0.6 * g("vigilance"), "join": g("sociability"),
                                            "challenge": max(0.0, g("dominance") - 0.5)}.get(name, 0.5), 0, 1))
        return Answer(probs, noul, 0.0, 0.0)

    async def ask(self, state: str, questions: dict) -> Answer:
        self.calls += 1
        start = time.perf_counter()
        if self.latency_s > 0:
            await asyncio.sleep(self.latency_s * float(self.rng.lognormal(0, 0.3)))
        if self.gate is not None:
            await self.gate.wait()
        a = self.distributions(state, questions)
        a.total_ms = a.model_ms = (time.perf_counter() - start) * 1000
        return a


# Сервер Kev отдаёт вероятности при температуре 2,35 (калибровка). Для выбора поведения её снимаем: p^2.35 и
# нормировка (E1: вероятность очевидного ответа 0,29 → 0,66, характеры различаются в десятки раз сильнее).
SHARPEN = 2.35


def sharpen(p: dict[str, float]) -> dict[str, float]:
    w = {k: v ** SHARPEN for k, v in p.items()}
    z = sum(w.values()) or 1.0
    return {k: v / z for k, v in w.items()}


class KevOracle:
    """Оракул Kev через eco/kev.py (сервер localhost:8009)."""

    def __init__(self, client: KevClient | None = None):
        self.client = client or KevClient(concurrency=256)
        self.calls = 0

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.client.__aexit__(*exc)

    async def ask(self, state: str, questions: dict) -> Answer:
        self.calls += 1
        a = await self.client.ask(state, questions)
        a.probabilities = {q: sharpen(p) for q, p in a.probabilities.items()}
        a.noul = {q: sharpen({"y": p, "n": 1.0 - p})["y"] for q, p in a.noul.items()}
        return a


# ---------------------------------------------------------------------- решатели поверх оракула
@dataclass
class Ask:
    i: int
    uid: int
    kind: int
    t_sent: float
    wall_sent: float
    state: str
    questions: dict
    tmap: dict
    key: tuple | None = None
    policy: bool = False
    waiting: list = field(default_factory=list)   # V5: запросы, ждущие политику
    task: asyncio.Task | None = None


POLICY_SIT = ["calm", "hungry", "threat", "night"]


class OracleSolver(Solver):
    """V1–V5 поверх оракула (Kev или Mock)."""

    def __init__(self, variant: str, oracle, seed: int = 0, observer: tuple[float, float] | None = None,
                 near_m: float = 60.0, far_m: float = 200.0, policy_ttl_s: float = 120.0):
        super().__init__(seed)
        self.name, self.oracle, self.variant = variant, oracle, variant
        self.v0 = UtilitySolver(seed + 1)
        self.cache: dict[tuple, Answer] = {}
        self.cache_hits = self.cache_miss = 0
        self.tiers = {"near": 0, "mid": 0, "far": 0, "far_v0": 0}
        self.observer = np.array(observer if observer else (0.0, 0.0))
        self.near_m, self.far_m, self.ttl = near_m, far_m, policy_ttl_s
        self.policy: dict[int, tuple[float, dict]] = {}
        self.policy_inflight: dict[int, Ask] = {}
        self.policy_hits = 0

    # --- ключ кэша: огрублённые поля state
    @staticmethod
    def cache_keys(sim: Sim, idx: np.ndarray, kind: np.ndarray) -> list[tuple]:
        f = features(sim, idx)
        b3 = lambda x: np.digitize(x, [0.3, 0.6])
        thr = np.where(f["near"], 2, f["threat"].astype(int))
        role = np.where(f["leader"], 2, np.where(f["member"] | f["has_lead"], 1, 0))
        cols = [f["sp"], kind, b3(f["h"]), b3(f["th"]), b3(f["fa"]), thr, role, f["night"].astype(int), b3(f["bold"]),
                f["alarm"].astype(int), f["prey_vis"].astype(int), f["solo_near"].astype(int), f["juv"].astype(int)]
        return [tuple(int(c) for c in row) for row in np.stack(cols, 1)]

    def _ask(self, sim: Sim, i: int, kind: int, key=None) -> Ask:
        q, tmap = questions_for(sim, i, kind)
        return Ask(int(i), int(sim.uid[i]), int(kind), sim.t, time.perf_counter(), state_text(sim, i, kind), q, tmap, key)

    def _from_answer(self, sim: Sim, i: int, uid: int, kind: int, ans: Answer, tmap: dict, source: str) -> Batch:
        """Одна строка Batch из распределений: семпл по каждому вопросу."""
        b = Batch.empty(1)
        b.idx[0], b.uid[0], b.kind[0] = i, uid, kind
        rng = self.rng
        pr, nl = ans.probabilities, ans.noul
        if "pattern" in pr:
            name = pick(rng, pr["pattern"])
            b.pattern[0] = P.get(name, -1)
            row = np.zeros(NP)
            for k, v in pr["pattern"].items():
                if k in P:
                    row[P[k]] = v
            b.pmat[0] = row / max(row.sum(), 1e-9)
        if "reaction" in pr:
            name = pick(rng, pr["reaction"])
            b.pattern[0] = S.REACTION_TO_PATTERN.get(name, -1)
        if "target" in pr and tmap:
            b.target[0] = tmap.get(pick(rng, pr["target"]), -1)
        elif S.IS_PRED[sim.sp[i]] and sim.alive[i]:
            b.target[0] = v0_target(sim, np.array([i]), rng)[0]
        b.alarm[0] = "alarm" in nl and rng.random() < nl["alarm"]
        b.join[0] = "join" in nl and rng.random() < nl["join"]
        b.challenge[0] = "challenge" in nl and rng.random() < nl["challenge"]
        b.source = [source]
        if self.want_detail:
            d = {"src": source}
            for k, v in pr.items():
                d[k] = {o: round(float(x), 3) for o, x in v.items()}
            for k, v in nl.items():
                d[k] = round(float(v), 3)
            b.detail = [d]
        return b

    def _cached(self, sim, idx, kind, keys) -> tuple[list[Batch], np.ndarray]:
        out, miss = [], np.ones(len(idx), bool)
        for j, (i, k, key) in enumerate(zip(idx, kind, keys)):
            a = self.cache.get(key)
            if a is None:
                continue
            q, tmap = questions_for(sim, i, k)
            out.append(self._from_answer(sim, int(i), int(sim.uid[i]), int(k), a, tmap, "cache"))
            miss[j] = False
        self.cache_hits += int((~miss).sum()); self.cache_miss += int(miss.sum())
        return out, miss

    def handle(self, sim: Sim, idx: np.ndarray, kind: np.ndarray) -> tuple[Batch, list[Ask]]:
        v = self.variant
        if not len(idx):
            return Batch.empty(), []
        if v == "V1":
            return Batch.empty(), [self._ask(sim, i, k) for i, k in zip(idx, kind)]
        if v == "V2":
            f = features(sim, idx)
            follow = (kind == KIND_PATTERN) & f["has_lead"] & ~f["leader"] & (f["sp"] != S.K["raven"])
            b = Batch.empty(int(follow.sum()))
            fi = idx[follow]
            b.idx, b.uid, b.kind = fi, sim.uid[fi], kind[follow]
            b.pattern[:] = P["follow"]
            b.source = ["follow"] * len(fi)
            if self.want_detail:
                b.detail = [{"src": "follow"} for _ in fi]
            return b, [self._ask(sim, i, k) for i, k in zip(idx[~follow], kind[~follow])]
        if v == "V3":
            keys = self.cache_keys(sim, idx, kind)
            hits, miss = self._cached(sim, idx, kind, keys)
            return Batch.concat(hits), [self._ask(sim, i, k, key) for i, k, key, m in zip(idx, kind, keys, miss) if m]
        if v == "V4":
            d = np.linalg.norm(sim.pos[idx] - self.observer, axis=1)
            tier = np.digitize(d, [self.near_m, self.far_m])            # 0 рядом, 1 средне, 2 далеко
            sim.interval_mul[idx] = np.array([1.0, 2.0, 4.0])[tier]
            self.tiers["near"] += int((tier == 0).sum()); self.tiers["mid"] += int((tier == 1).sum())
            self.tiers["far"] += int((tier == 2).sum())
            keys = self.cache_keys(sim, idx, kind)
            asks = [self._ask(sim, i, k, key) for i, k, key, t in zip(idx, kind, keys, tier) if t == 0]
            rest = tier > 0
            hits, miss = self._cached(sim, idx[rest], kind[rest], [k for k, r in zip(keys, rest) if r])
            ri, rk = idx[rest], kind[rest]
            rkeys = [k for k, r in zip(keys, rest) if r]
            mid_miss = miss & (tier[rest] == 1)
            far_miss = miss & (tier[rest] == 2)
            asks += [self._ask(sim, i, k, key) for i, k, key, m in zip(ri, rk, rkeys, mid_miss) if m]
            self.tiers["far_v0"] += int(far_miss.sum())
            v0 = self.v0.decide(sim, ri[far_miss], rk[far_miss], source="far_v0")
            return Batch.concat(hits + [v0]), asks
        if v == "V5":
            out, asks = [], []
            for i, k in zip(idx, kind):
                u = int(sim.uid[i])
                pol = self.policy.get(u)
                if pol and sim.t - pol[0] < self.ttl:
                    out.append(self._from_policy(sim, int(i), int(k), pol[1]))
                    self.policy_hits += 1
                elif u in self.policy_inflight:
                    self.policy_inflight[u].waiting.append((int(i), int(k)))
                else:
                    a = self._policy_ask(sim, int(i))
                    a.waiting.append((int(i), int(k)))
                    self.policy_inflight[u] = a
                    asks.append(a)
            return Batch.concat(out), asks
        raise ValueError(v)

    # --- V5: личная политика
    def _policy_ask(self, sim: Sim, i: int) -> Ask:
        s = int(sim.sp[i])
        ch = S.pattern_choices(s)
        ch.pop("investigate", None)
        q = {f"pattern_{sit}": {"type": "choice", "criteria": ch} for sit in POLICY_SIT}
        state = state_text(sim, i, KIND_PATTERN).rsplit("\n", 1)[0] + \
            "\nquestion: for each situation (calm, hungry or thirsty, danger nearby, night) choose what this animal does"
        return Ask(i, int(sim.uid[i]), KIND_PATTERN, sim.t, time.perf_counter(), state, q, {}, policy=True)

    @staticmethod
    def situation(sim: Sim, i: int) -> str:
        if sim.thr[i] >= 0 or sim.t - sim.ev_t[i, EV_ALARM] < 5 or sim.t - sim.ev_t[i, EV_GROUP] < 5:
            return "threat"
        if max(sim.hunger[i], sim.thirst[i]) > 0.5:
            return "hungry"
        return "night" if sim.light() < 0.2 else "calm"

    def _from_policy(self, sim: Sim, i: int, kind: int, pol: dict) -> Batch:
        sit = self.situation(sim, i)
        b = self.v0.decide(sim, np.array([i]), np.array([kind]), source="policy")
        dist = dict(pol.get(f"pattern_{sit}", {}))
        if sit == "hungry" and sim.thirst[i] > sim.hunger[i] and "drink" in dist:   # в «голод/жажда» — нужная из двух
            dist.pop("graze", None)
        elif sit == "hungry":
            dist.pop("drink", None)
        if dist:
            name = pick(self.rng, dist)
            b.pattern[0] = P[name]
            row = np.zeros(NP)
            for k, v in dist.items():
                row[P[k]] = v
            b.pmat[0] = row / max(row.sum(), 1e-9) if kind == KIND_PATTERN else np.nan
            if self.want_detail:
                b.detail = [{"src": "policy", "situation": sit, "pattern": {k: round(v, 3) for k, v in dist.items()}}]
        return b

    def resolve(self, sim: Sim, ask: Ask, ans: Answer) -> Batch:
        if ask.policy:
            self.policy[ask.uid] = (sim.t, ans.probabilities)
            self.policy_inflight.pop(ask.uid, None)
            return Batch.concat([self._from_policy(sim, i, k, ans.probabilities) for i, k in ask.waiting
                                 if sim.alive[i] and sim.uid[i] == ask.uid])
        if ask.key is not None:
            self.cache[ask.key] = ans
        return self._from_answer(sim, ask.i, ask.uid, ask.kind, ans, ask.tmap, "oracle")

    def fail(self, sim: Sim, ask: Ask) -> Batch:
        """Оракул не ответил: запрос закрывается без смены паттерна."""
        self.policy_inflight.pop(ask.uid, None)
        pairs = ask.waiting if ask.policy else [(ask.i, ask.kind)]
        b = Batch.empty(len(pairs))
        for j, (i, k) in enumerate(pairs):
            b.idx[j], b.uid[j], b.kind[j] = i, ask.uid, k
        b.source = ["error"] * len(pairs)
        return b


def make_solver(variant: str, oracle=None, seed: int = 0, observer=None) -> Solver:
    if variant == "random":
        return RandomSolver(seed)
    if variant == "V0":
        return UtilitySolver(seed)
    return OracleSolver(variant, oracle, seed, observer)


# ---------------------------------------------------------------------- драйвер
class Driver:
    """Шаг симуляции + решения. batched: такт ждёт все ответы оракула. realtime: ответ применяется, когда пришёл;
    реакция, применённая позже 0,3 с симуляционного времени после события, — опоздавшая."""
    LATE_S = 0.3

    def __init__(self, sim: Sim, solver: Solver, mode: str = "batched", metrics=None, recorder=None):
        self.sim, self.solver, self.mode, self.metrics, self.recorder = sim, solver, mode, metrics, recorder
        solver.want_detail = recorder is not None
        self.inflight: list[Ask] = []
        self.errors = 0

    def _apply(self, b: Batch, delays: np.ndarray | None = None):
        if not len(b.idx):
            return
        ok = self.sim.apply(b.idx, b.uid, b.kind, b.pattern, b.target, b.alarm, b.join, b.challenge)
        if self.metrics:
            self.metrics.on_apply(self.sim, b, ok, delays)
        if self.recorder:
            self.recorder.on_apply(self.sim, b, ok)

    async def tick(self):
        sim = self.sim
        sim.step()
        idx, kind = sim.take_requests()
        if len(idx) and self.metrics:
            self.metrics.on_request(kind)
        b, asks = self.solver.handle(sim, idx, kind)
        self._apply(b, np.zeros(len(b.idx)))
        oracle = self.solver.oracle
        for a in asks:
            a.task = asyncio.ensure_future(oracle.ask(a.state, a.questions))
            self.inflight.append(a)
        if self.metrics and asks:
            self.metrics.on_ask(asks)
        if self.mode == "batched" and self.inflight:
            await asyncio.wait([a.task for a in self.inflight])
        elif self.inflight:
            await asyncio.sleep(0)
        self._collect()
        if self.metrics and sim.tick % self.metrics.sample_every == 0:
            self.metrics.sample(sim)
        if self.recorder:
            self.recorder.maybe_frame(sim)

    def _collect(self):
        done = [a for a in self.inflight if a.task.done()]
        if not done:
            return
        self.inflight = [a for a in self.inflight if not a.task.done()]
        out, delays = [], []
        for a in done:
            if a.task.exception() is not None:
                self.errors += 1
                b = self.solver.fail(self.sim, a)
            else:
                ans = a.task.result()
                if self.metrics:
                    self.metrics.on_answer(ans)
                b = self.solver.resolve(self.sim, a, ans)
            out.append(b)
            delays += [self.sim.t - a.t_sent] * len(b.idx)
        self._apply(Batch.concat(out), np.array(delays))

    async def run(self, days: float, realtime: bool = False, on_day=None):
        """realtime — такт по стене часов (10 Гц); иначе как можно быстрее."""
        sim = self.sim
        end = sim.t + days * sim.day_s
        start_wall, start_t = time.perf_counter(), sim.t
        next_day = int(sim.day) + 1
        while sim.t < end - 1e-9:
            await self.tick()
            if realtime:
                lag = (sim.t - start_t) - (time.perf_counter() - start_wall)
                if lag > 0:
                    await asyncio.sleep(lag)
                    self._collect()
            if on_day and sim.day >= next_day:
                on_day(sim)
                next_day += 1
        if self.inflight:
            for a in self.inflight:
                a.task.cancel()
            await asyncio.gather(*(a.task for a in self.inflight), return_exceptions=True)
            self.inflight = []
