"""Замеры прогона: скорость решений, задержки, опоздания, экосистема, разнообразие выбора."""
import time
from collections import Counter

import numpy as np

from eco import species as S
from eco.sim import EV_THREAT, KIND_PATTERN, KIND_REACTION, Sim

NP = len(S.PATTERNS)


def pct(v: list[float], p: float) -> float | None:
    return float(np.percentile(v, p)) if len(v) else None


def entropy(p: np.ndarray) -> float:
    p = p[p > 0] / p.sum()
    return float(-(p * np.log2(p)).sum())


def js_div(p: np.ndarray, q: np.ndarray) -> float:
    """Дивергенция Йенсена — Шеннона, биты (0 — одинаковые распределения, 1 — не пересекаются)."""
    p = p / p.sum(); q = q / q.sum(); m = (p + q) / 2
    kl = lambda a, b: float((a[a > 0] * np.log2(a[a > 0] / b[a > 0])).sum())
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def situation(sim: Sim, idx: np.ndarray) -> np.ndarray:
    """Огрублённая ситуация для сравнения характеров: голод, жажда, угроза, ночь — 16 классов."""
    return ((sim.hunger[idx] > 0.5) * 1 + (sim.thirst[idx] > 0.5) * 2 + (sim.thr[idx] >= 0) * 4
            + (sim.light() < 0.2) * 8).astype(int)


class Metrics:
    def __init__(self, sim: Sim, mode: str):
        self.mode = mode
        self.wall0 = time.perf_counter()
        self.t0 = sim.t
        self.requested = Counter()
        self.served = Counter()
        self.asked = 0
        self.model_ms: list[float] = []
        self.road_ms: list[float] = []
        self.rea_delay: list[float] = []
        self.choice = np.zeros((S.NS, NP))
        self.psum = np.zeros((S.NS, NP))
        self.ent = np.zeros(S.NS)
        self.nent = np.zeros(S.NS)
        self.js = np.zeros((S.NS, 16, 3, NP))
        self.jsn = np.zeros((S.NS, 16, 3))
        self.pop_day: list[float] = []
        self.pop: list[list[int]] = []
        self.groups: list[tuple[float, int, float]] = []
        self.sample_every = max(1, int(sim.day_s / sim.dt / 24))     # раз в игровой час

    def on_request(self, kind: np.ndarray):
        self.requested["pattern"] += int((kind == KIND_PATTERN).sum())
        self.requested["reaction"] += int((kind == KIND_REACTION).sum())

    def on_ask(self, asks):
        self.asked += len(asks)

    def on_answer(self, ans):
        """Задержка модели (latency_ms сервера) и с дороги (HTTP-запрос целиком, замер клиента)."""
        self.model_ms.append(ans.model_ms)
        self.road_ms.append(ans.total_ms)

    def on_apply(self, sim: Sim, b, ok: np.ndarray, delays: np.ndarray | None):
        for s, c in Counter(b.source).items():
            self.served[s] += c
        if delays is not None and len(delays):
            src = np.array(b.source)
            m = (b.kind == KIND_REACTION) & ((src == "oracle") | (src == "policy"))
            self.rea_delay += list(delays[m])
        m = ok & (b.kind == KIND_PATTERN) & ~np.isnan(b.pmat[:, 0]) & (b.pattern >= 0)
        if not m.any():
            return
        idx = b.idx[m]
        sp = sim.sp[idx]
        pm = b.pmat[m]
        np.add.at(self.choice, (sp, b.pattern[m]), 1)
        np.add.at(self.psum, sp, pm)
        with np.errstate(divide="ignore", invalid="ignore"):
            e = -np.nansum(np.where(pm > 0, pm * np.log2(pm), 0), 1)
        np.add.at(self.ent, sp, e); np.add.at(self.nent, sp, 1)
        sit = situation(sim, idx)
        bb = np.digitize(sim.traits[idx, 0], [0.33, 0.67])
        np.add.at(self.js, (sp, sit, bb), pm)
        np.add.at(self.jsn, (sp, sit, bb), 1)

    def sample(self, sim: Sim):
        self.pop_day.append(round(sim.day, 3))
        self.pop.append(sim.count().tolist())
        live = sim.alive & (sim.grp >= 0)
        if live.any():
            cnt = np.bincount(sim.grp[live])
            cnt = cnt[cnt > 0]
            self.groups.append((sim.day, int(len(cnt)), float(cnt.mean())))

    def report(self, sim: Sim, solver, extra: dict | None = None) -> dict:
        wall = time.perf_counter() - self.wall0
        sim_s = sim.t - self.t0
        days = sim_s / sim.day_s
        st = sim.stats
        keys = [S.KEYS[s] for s in sim.species]
        deaths = {k: {} for k in keys}
        for (k, cause), c in st["deaths"].items():
            deaths.setdefault(k, {})[cause] = c
        req = sum(self.requested.values())
        srv = sum(self.served.values())
        late = [d for d in self.rea_delay if d > 0.3 + 1e-9]
        by_sp = {}
        for s in sim.species:
            k = S.KEYS[s]
            n = self.choice[s].sum()
            js = []
            for sit in range(16):
                if self.jsn[s, sit, 0] >= 20 and self.jsn[s, sit, 2] >= 20:
                    js.append((js_div(self.js[s, sit, 0], self.js[s, sit, 2]), self.jsn[s, sit, [0, 2]].sum()))
            by_sp[k] = {
                "pattern_choices": {S.PATTERNS[p]: int(self.choice[s, p]) for p in range(NP) if self.choice[s, p]},
                "choice_entropy_bits": entropy(self.choice[s]) if n else None,
                "mean_decision_entropy_bits": float(self.ent[s] / self.nent[s]) if self.nent[s] else None,
                "js_bold_vs_timid_bits": float(np.average([j for j, _ in js], weights=[w for _, w in js])) if js else None,
                "js_situations": len(js),
                "hunts": st["hunts"].get(k, 0), "kills": st["kills"].get(k, 0),
                "hunt_success": st["kills"].get(k, 0) / st["hunts"][k] if st["hunts"].get(k) else None,
                "births": st["births"].get(k, 0), "deaths": deaths.get(k, {}),
                "final": int(sim.count()[s]),
            }
        lt = st["group_lifetimes"]
        rep = {
            "variant": solver.name, "time_mode": self.mode, "animals_start": int(self.pop[0] and sum(self.pop[0])) if self.pop else None,
            "animals_final": int(sim.alive.sum()), "world_m": sim.size, "day_seconds": sim.day_s, "year_days": sim.year_days,
            "wall_s": wall, "sim_days": days, "game_days_per_wall_min": days / wall * 60 if wall else None,
            "ticks_per_wall_s": sim_s / sim.dt / wall if wall else None,
            "decisions": {
                "requested": dict(self.requested), "served": dict(self.served), "oracle_asks": self.asked,
                "requested_per_sim_s": req / sim_s if sim_s else None, "served_per_sim_s": srv / sim_s if sim_s else None,
                "requested_per_wall_s": req / wall, "served_per_wall_s": srv / wall, "asks_per_wall_s": self.asked / wall,
            },
            "latency_ms": {"model": {p: pct(self.model_ms, q) for p, q in (("p50", 50), ("p95", 95), ("p99", 99))},
                           "road": {p: pct(self.road_ms, q) for p, q in (("p50", 50), ("p95", 95), ("p99", 99))}},
            "reactions_from_oracle": len(self.rea_delay),
            "late_reaction_share": (len(late) / len(self.rea_delay) if self.rea_delay else None) if self.mode == "realtime" else None,
            "reaction_delay_sim_s": {p: pct(self.rea_delay, q) for p, q in (("p50", 50), ("p95", 95), ("p99", 99))},
            "species": by_sp,
            "population": {"day": self.pop_day, **{k: [row[S.K[k]] for row in self.pop] for k in keys}},
            "groups": {
                "mean_count": float(np.mean([g[1] for g in self.groups])) if self.groups else 0,
                "mean_size": float(np.mean([g[2] for g in self.groups])) if self.groups else 0,
                "dissolved": len(lt), "lifetime_days_median": float(np.median(lt)) if lt else None,
                "leader_changes": {f"{k}:{c}": v for (k, c), v in st["leader_changes"].items()},
                "challenges": st["challenges"], "joins": st["joins"], "merges": st["merges"], "splits": st["splits"],
            },
            "alarms": {"jay_calls": st["alarms"], "heard": st["alarm_heard"], "group_alarms": st["group_alarms"]},
            "reflexes": st["reflexes"], "events": dict(st["events"]),
        }
        v = solver.name
        if v in ("V3", "V4"):
            h, m = solver.cache_hits, solver.cache_miss
            rep["cache"] = {"hits": h, "misses": m, "hit_rate": h / (h + m) if h + m else None, "keys": len(solver.cache)}
        if v == "V4":
            rep["attention_tiers"] = solver.tiers
        if v == "V5":
            rep["policy"] = {"hits": solver.policy_hits, "animals": len(solver.policy)}
        if extra:
            rep.update(extra)
        return rep
