"""Запись прогона в JSONL для просмотрщика sim/ecosystem/viewer.html.

Первая строка — header: размер мира, карта леса и воды (0–9 на клетку), норы, виды, паттерны.
Дальше — кадр раз в every тактов: особи (uid, вид, x, y, текущее занятие, вожак ли) и решения с прошлого кадра
(uid -> вероятности по вопросам и выбранное).
"""
import json

import numpy as np

from eco import species as S
from eco.sim import KIND_PATTERN, Sim


def _grid(a: np.ndarray, n: int) -> list[str]:
    step = max(1, int(np.ceil(a.shape[0] / n)))
    m = a[::step, ::step]
    return ["".join(str(int(v)) for v in row) for row in np.clip(np.round(m * 9), 0, 9)]


class Recorder:
    def __init__(self, path: str, sim: Sim, every: int = 10, grid: int = 200):
        self.f = open(path, "w", encoding="utf-8")
        self.every = every
        self.pending: dict[int, dict] = {}
        w = sim.world
        hdr = {"type": "header", "size": sim.size, "day_seconds": sim.day_s, "year_days": sim.year_days,
               "forest": _grid(w.forest, grid), "water": _grid(w.water.astype(float), grid),
               "dens": np.round(w.dens, 1).tolist(),
               "species": [{"key": s["key"], "name": s["name"]} for s in S.SPECIES], "patterns": S.PATTERNS}
        self.f.write(json.dumps(hdr) + "\n")

    def on_apply(self, sim: Sim, b, ok: np.ndarray):
        if b.detail is None:
            return
        for j in np.flatnonzero(ok):
            d = dict(b.detail[j] or {})
            p = int(b.pattern[j])
            d["chosen"] = S.PATTERNS[p] if p >= 0 else "continue"
            d["kind"] = "pattern" if b.kind[j] == KIND_PATTERN else "reaction"
            d["t"] = round(sim.t, 1)
            if b.target[j] >= 0:
                d["target"] = int(sim.uid[b.target[j]])
            if b.alarm[j]:
                d["alarm_called"] = True
            self.pending[int(b.uid[j])] = d

    def maybe_frame(self, sim: Sim):
        if sim.tick % self.every:
            return
        a = np.flatnonzero(sim.alive)
        leader = np.zeros(len(a), bool)
        if len(sim.g_leader):
            g = sim.grp[a]
            leader = (g >= 0) & (sim.g_leader[np.maximum(g, 0)] == a)
        fr = {"type": "frame", "t": round(sim.t, 1), "day": round(sim.day, 3), "daypart": sim.daypart(),
              "season": S.SEASONS[sim.season()], "uid": sim.uid[a].tolist(), "sp": sim.sp[a].tolist(),
              "x": np.round(sim.pos[a, 0], 1).tolist(), "y": np.round(sim.pos[a, 1], 1).tolist(),
              "p": sim.act[a].tolist(), "g": sim.grp[a].tolist(), "L": np.flatnonzero(leader).tolist(),
              "dec": {str(k): v for k, v in self.pending.items()}}
        self.pending = {}
        self.f.write(json.dumps(fr) + "\n")

    def close(self):
        self.f.close()
