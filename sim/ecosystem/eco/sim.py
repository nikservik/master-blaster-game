"""Механика экосистемы — векторно, struct of arrays по особям.

Такт dt = 0,1 с. Каждый такт: рефлекс, охота, движение. Раз в perc_every тактов: восприятие, события, управление
паттернами, еда и потребности, запросы решений. Раз в секунду: группы, размножение, старение и смерти, отрастание.
Решения принимает решатель снаружи (eco.decide): Sim отдаёт запросы (take_requests) и принимает ответы (apply).
"""
from collections import Counter

import numpy as np
from scipy.spatial import cKDTree

from eco import species as S
from eco.species import P
from eco.world import World

EV_THREAT, EV_ALARM, EV_GROUP, EV_PREY = range(4)
EVENTS = ["saw predator", "heard jay alarm", "group alarm", "saw prey"]
KIND_PATTERN, KIND_REACTION = 0, 1
EAT_ACTS = [P["graze"], P["scavenge"], P["hunt"], P["ambush"]]
RING = np.stack([np.cos(np.arange(8) * np.pi / 4), np.sin(np.arange(8) * np.pi / 4)], axis=1)

_FIELDS = [  # имя, хвост формы, тип, начальное значение
    ("alive", (), bool, False), ("uid", (), np.int64, -1), ("sp", (), np.int16, 0), ("sex", (), np.int8, 0),
    ("age", (), float, 0.0), ("life", (), float, 1.0), ("pos", (2,), float, 0.0), ("dir", (2,), float, 0.0),
    ("spd", (), float, 0.0), ("hunger", (), float, 0.2), ("thirst", (), float, 0.2), ("fatigue", (), float, 0.1),
    ("health", (), float, 1.0), ("stamina", (), float, 1.0), ("traits", (5,), float, 0.5), ("phys", (4,), float, 1.0),
    ("pattern", (), np.int8, 6), ("act", (), np.int8, 6), ("pattern_t", (), float, 0.0), ("next_decide", (), float, 0.0),
    ("last_decide", (), float, -1e9), ("done", (), bool, False), ("pend_pat", (), bool, False), ("pend_rea", (), bool, False),
    ("lock_until", (), float, -1e9), ("target", (), np.int64, -1), ("target_uid", (), np.int64, -1),
    ("hunt_chase", (), bool, False), ("hunt_seen", (), float, 0.0), ("hunt_start", (), float, 0.0),
    ("flee_from", (2,), float, 0.0), ("inv_pt", (2,), float, 0.0), ("mem_water", (2,), float, np.nan),
    ("mem_food", (2,), float, np.nan), ("mem_pred", (2,), float, np.nan), ("mem_pred_t", (), float, -1e9),
    ("home", (2,), float, 0.0), ("grp", (), np.int64, -1), ("rank", (), np.int32, 0), ("mother", (), np.int64, -1),
    ("mother_uid", (), np.int64, -1), ("pregnant", (), bool, False), ("due", (), float, 0.0), ("father", (9,), float, 1.0),
    ("last_birth", (), float, -1e9), ("thr", (), np.int64, -1), ("thr_d", (), float, np.inf), ("thr_mode", (), np.int8, 0),
    ("prey", (4,), np.int64, -1), ("prey_d", (4,), float, np.inf), ("cons", (), np.int64, -1), ("cons_d", (), float, np.inf),
    ("near_wolf", (), np.int64, -1), ("ev_t", (4,), float, -1e9), ("ev_new", (4,), bool, False), ("ev_src", (2,), float, 0.0),
    ("alarm_heard", (), float, -1e9), ("want_join", (), float, -1e9), ("want_chal", (), bool, False),
    ("interval_mul", (), float, 1.0), ("last_call", (), float, -1e9), ("_want", (), float, 0.0),
    ("_lead", (), np.int64, -1), ("_gs", (), float, 1.0),
]
TRAITS = ["boldness", "curiosity", "sociability", "dominance", "vigilance"]
PHYS = ["speed", "stamina", "strength", "senses"]


class Sim:
    def __init__(self, n_animals: int, seed: int = 0, species: list[str] | None = None, size: float | None = None,
                 day_seconds: float = 600.0, year_days: float = 12.0, dt: float = 0.1, productivity: float = 1.0,
                 perc_every: int = 3):
        species = species or S.BASE
        self.rng = np.random.default_rng(seed)
        self.size = size or 500.0 * np.sqrt(max(n_animals, 1) / 1000.0)
        self.world = World(self.size, seed, productivity)
        self._den_tree = cKDTree(self.world.dens)
        self.dt, self.day_s, self.year_days, self.perc_every = dt, day_seconds, year_days, perc_every
        self.t, self.tick, self.next_uid = 0.0, 0, 0
        self.species = [S.K[k] for k in species]
        self._alloc(max(64, int(n_animals * 1.5)))
        # Группы: таблицы, растущие по мере надобности.
        self.g_alive = np.zeros(0, bool); self.g_leader = np.zeros(0, np.int64); self.g_sp = np.zeros(0, np.int16)
        self.g_born = np.zeros(0); self.g_center = np.zeros((0, 2)); self.g_last_chal = np.zeros(0)
        self.stats = dict(deaths=Counter(), births=Counter(), hunts=Counter(), kills=Counter(), leader_changes=Counter(),
                          group_lifetimes=[], alarms=0, alarm_heard=0, reflexes=0, group_alarms=0, challenges=0,
                          joins=0, merges=0, splits=0, events=Counter())
        self.requests: list[tuple[np.ndarray, np.ndarray]] = []
        self._populate(n_animals, species)

    # ------------------------------------------------------------------ хранение
    def _alloc(self, cap: int):
        for name, tail, dt, fill in _FIELDS:
            old = getattr(self, name, None)
            a = np.full((cap,) + tail, fill, dtype=dt)
            if old is not None:
                a[:len(old)] = old
            setattr(self, name, a)
        self.cap = cap

    def _spawn(self, sp: np.ndarray, pos: np.ndarray, age: np.ndarray, traits: np.ndarray, phys: np.ndarray) -> np.ndarray:
        n = len(sp)
        free = np.flatnonzero(~self.alive)
        if len(free) < n:
            self._alloc(max(self.cap * 2, self.cap + n))
            free = np.flatnonzero(~self.alive)
        ix = free[:n]
        for name, tail, dt, fill in _FIELDS:
            getattr(self, name)[ix] = fill
        yd = self.year_days
        self.alive[ix] = True
        self.uid[ix] = np.arange(self.next_uid, self.next_uid + n); self.next_uid += n
        self.sp[ix] = sp; self.sex[ix] = self.rng.integers(0, 2, n); self.age[ix] = age
        self.life[ix] = S.LIFESPAN[sp] * yd * np.clip(self.rng.normal(1, 0.15, n), 0.5, 1.4)
        self.pos[ix] = np.clip(pos, 0.5, self.size - 0.5)
        ang = self.rng.random(n) * 2 * np.pi
        self.dir[ix] = np.stack([np.cos(ang), np.sin(ang)], 1)
        self.traits[ix] = traits; self.phys[ix] = phys
        self.next_decide[ix] = self.t + self.rng.random(n) * 5
        self.pattern_t[ix] = self.t
        self.mem_water[ix] = self.world.water_near[self.world.cell(self.pos[ix])]   # свой участок: ближайшая вода известна
        self.home[ix] = self.world.dens[self._den_tree.query(self.pos[ix])[1]]
        return ix

    def _new_traits(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        return self.rng.beta(2, 2, (n, 5)), np.clip(self.rng.normal(1, 0.08, (n, 4)), 0.7, 1.3)

    def add(self, key: str, pos, age_years: float | None = None, sex: int | None = None, **values) -> int:
        """Одна особь в точке pos (сценарии и тесты). values — начальные значения полей: hunger=0.9, pattern=..."""
        s = S.K[key]
        age = S.MATURITY[s] * 1.5 if age_years is None else age_years
        tr, ph = self._new_traits(1)
        i = int(self._spawn(np.array([s]), np.array([pos], float), np.array([age * self.year_days]), tr, ph)[0])
        if sex is not None:
            self.sex[i] = sex
        for k, v in values.items():
            getattr(self, k)[i] = v
            if k == "pattern":
                self.act[i] = v
        return i

    def _populate(self, n: int, keys: list[str]):
        if n == 0:
            return
        share = S.SHARE_BASE if set(keys) <= set(S.BASE) else S.SHARE_ALL
        w = np.array([share.get(k, 0.05) for k in keys]); w /= w.sum()
        counts = np.maximum(1, np.round(w * n).astype(int))
        yd = self.year_days
        for k, c in zip(keys, counts):
            s = S.K[k]
            sp = np.full(c, s)
            juv = self.rng.random(c) < 0.2
            age = np.where(juv, self.rng.random(c) * S.MATURITY[s], S.MATURITY[s] + self.rng.random(c) * 0.5 * S.LIFESPAN[s]) * yd
            pos = self.rng.random((c, 2)) * self.size
            if S.SOCIAL[s]:  # стада, стаи, пары: соседи рядом с вожаком
                gsize = max(2, min(S.GROUP_MAX[s], {"herd": 4, "pack": 5, "pair": 2}[S.SPECIES[s]["social"]]))
                lead = np.arange(c) // gsize * gsize
                pos = pos[lead] + self.rng.normal(0, 5, (c, 2))
            ix = self._spawn(sp, pos, age, *self._new_traits(c))
            self.hunger[ix] = self.rng.random(c) * 0.4; self.thirst[ix] = self.rng.random(c) * 0.4
            if S.SOCIAL[s]:
                for g0 in range(0, c, gsize):
                    members = ix[g0:g0 + gsize]
                    if len(members) > 1:
                        self._new_group(members)
            # Весенний приплод: самки видов с гоном до весны уже беременны.
            if not S.MATE[s, 0]:
                fem = ix[(self.sex[ix] == 0) & (self.age[ix] >= S.MATURITY[s] * yd)]
                if S.TERRITORIAL[s]:   # в стае рожает одна самка
                    fem = fem[np.unique(self.grp[fem], return_index=True)[1]]
                self.pregnant[fem] = True
                self.due[fem] = self.rng.random(len(fem)) * self.day_s * yd / 8
                self.father[fem] = np.concatenate(self._new_traits(len(fem)), 1)

    # ------------------------------------------------------------------ время
    @property
    def day(self) -> float:
        return self.t / self.day_s

    def time_of_day(self) -> float:
        return (self.day + 0.3) % 1.0

    def light(self) -> float:
        return float(np.clip(1.5 * (np.sin(2 * np.pi * (self.time_of_day() - 0.25)) + 0.2), 0, 1))

    def daypart(self) -> str:
        l, h = self.light(), self.time_of_day()
        return "night" if l < 0.1 else ("day" if l > 0.9 else ("dawn" if h < 0.5 else "dusk"))

    def season(self) -> int:
        return int((self.day % self.year_days) / (self.year_days / 4)) % 4

    # ------------------------------------------------------------------ такт
    def step(self):
        self.t += self.dt
        self.tick += 1
        if self.tick % self.perc_every == 0:
            dts = self.dt * self.perc_every
            self._perceive()
            self._steer()
            self._needs(dts)
            self._triggers()
        self._reflex()
        self._hunt()
        self._move()
        if self.tick % int(round(1 / self.dt)) == 0:
            self._groups()
            self._life(1.0 / self.day_s)
            self.world.grow(1.0 / self.day_s, self.season())

    def count(self) -> np.ndarray:
        return np.bincount(self.sp[self.alive], minlength=S.NS)

    # ------------------------------------------------------------------ восприятие
    def _perceive(self):
        A, pos, sp, w = self.alive, self.pos, self.sp, self.world
        idx_s = [np.flatnonzero(A & (sp == s)) for s in range(S.NS)]
        trees = [cKDTree(pos[ix]) if len(ix) else None for ix in idx_s]
        light = self.light()
        forest = w.forest_at(pos)
        moving = self.spd > 0.3 * S.WALK[sp]
        running = self.spd > 0.5 * S.RUN[sp]
        act = self.act
        hid = np.where(np.isin(act, [P["hide"], P["ambush"]]) | ((act == P["hunt"]) & ~self.hunt_chase), 0.35, 1.0)
        den_rest = (act == P["rest"]) & S.DEN[sp] & (np.abs(pos - self.home).sum(1) < 4)
        hid = np.where(den_rest, 0.1, hid)
        size_f = np.clip(0.3 + 0.25 * np.log10(S.MASS[sp] * 10), 0.3, 1.2)
        self._vis_tgt = (1 - 0.6 * forest * ~S.FLYING[sp]) * hid * np.where(moving, 1.0, 0.6) * size_f
        sense = self.phys[:, 3]
        self._rng_vis = S.VISION[sp] * sense * (light + (1 - light) * S.NIGHT[sp]) * (0.75 + 0.5 * self.traits[:, 4])
        self._rng_hear = S.HEARING[sp] * sense
        self._rng_smell = S.SMELL[sp] * sense * 0.5
        self._running = running
        self._moving = moving

        def detect(o, tg, d):
            seen = d < self._rng_vis[o] * self._vis_tgt[tg]
            heard = (running[tg] & ~S.SILENT[sp[tg]]) & (d < self._rng_hear[o])
            heard |= moving[tg] & ~S.SILENT[sp[tg]] & (d < self._rng_hear[o] * 0.3)
            smelled = d < self._rng_smell[o]
            mode = np.where(seen, 1, np.where(heard, 2, np.where(smelled, 3, 0)))
            return mode > 0, mode

        t = self.t
        # Угрозы
        for s in range(S.NS):
            ix = idx_s[s]
            fears = np.flatnonzero(S.FEARS[s])
            if not len(ix) or not len(fears):
                continue
            R = max(S.VISION[s], S.HEARING[s], S.SMELL[s]) * 1.4
            best_d = np.full(len(ix), np.inf); best_j = np.full(len(ix), -1); best_m = np.zeros(len(ix), np.int8)
            for p in fears:
                if trees[p] is None:
                    continue
                d, j = trees[p].query(pos[ix], k=1, distance_upper_bound=R)
                ok = j < len(idx_s[p])
                cand = np.where(ok, idx_s[p][np.minimum(j, len(idx_s[p]) - 1)], -1)
                det, mode = detect(ix, np.maximum(cand, 0), d)
                det &= ok
                better = det & (d < best_d)
                best_d[better] = d[better]; best_j[better] = cand[better]; best_m[better] = mode[better]
            found = best_j >= 0
            self.thr[ix] = best_j; self.thr_d[ix] = best_d; self.thr_mode[ix] = best_m
            fi = ix[found]
            self.ev_new[fi, EV_THREAT] = t - self.ev_t[fi, EV_THREAT] > 10
            self.ev_t[fi, EV_THREAT] = t
            self.ev_src[fi] = pos[best_j[found]]
            self.mem_pred[fi] = pos[best_j[found]]; self.mem_pred_t[fi] = t
        # Добыча у хищников
        for pk, qs in S.PREY.items():
            p = S.K[pk]
            ix = idx_s[p]
            if not len(ix):
                continue
            R = max(S.VISION[p], S.HEARING[p], S.SMELL[p]) * 1.2
            ds, js = [], []
            for qk in qs:
                q = S.K[qk]
                if trees[q] is None:
                    continue
                k = min(4, len(idx_s[q]))
                d, j = trees[q].query(pos[ix], k=k, distance_upper_bound=R)
                d = d.reshape(len(ix), k); j = j.reshape(len(ix), k)
                ok = j < len(idx_s[q])
                cand = np.where(ok, idx_s[q][np.minimum(j, len(idx_s[q]) - 1)], -1)
                det, _ = detect(np.repeat(ix[:, None], k, 1), np.maximum(cand, 0), d)
                det &= ok
                ds.append(np.where(det, d, np.inf)); js.append(np.where(det, cand, -1))
            if not ds:
                self.prey[ix] = -1; self.prey_d[ix] = np.inf
                continue
            D = np.concatenate(ds, 1); J = np.concatenate(js, 1)
            if D.shape[1] < 4:
                D = np.pad(D, ((0, 0), (0, 4 - D.shape[1])), constant_values=np.inf)
                J = np.pad(J, ((0, 0), (0, 4 - J.shape[1])), constant_values=-1)
            o = np.argsort(D, 1)[:, :4]
            self.prey_d[ix] = np.take_along_axis(D, o, 1); self.prey[ix] = np.take_along_axis(J, o, 1)
            has = self.prey[ix, 0] >= 0
            fi = ix[has & (self.hunger[ix] > 0.4) & ~np.isin(self.act[ix], [P["hunt"], P["scavenge"]])]
            self.ev_new[fi, EV_PREY] = t - self.ev_t[fi, EV_PREY] > 20
            self.ev_t[fi, EV_PREY] = t
            self.ev_src[fi] = pos[self.prey[fi, 0]]
            # Охота: цель ещё видна?
            hunting = ix[self.target[ix] >= 0]
            seen = (self.prey[hunting] == self.target[hunting, None]).any(1)
            dt_ = np.linalg.norm(pos[np.maximum(self.target[hunting], 0)] - pos[hunting], axis=1)
            seen |= dt_ < self._rng_smell[hunting] + 5
            self.hunt_seen[hunting[seen]] = t
        # Ближайший сородич (для групп) и ближайший волк (для ворона)
        for s in range(S.NS):
            ix = idx_s[s]
            if S.SOCIAL[s] and len(ix) > 1:
                d, j = trees[s].query(pos[ix], k=2, distance_upper_bound=40)
                ok = j[:, 1] < len(ix)
                self.cons[ix] = np.where(ok, ix[np.minimum(j[:, 1], len(ix) - 1)], -1); self.cons_d[ix] = d[:, 1]
        rv, wv = idx_s[S.K["raven"]], idx_s[S.K["wolf"]]
        if len(rv) and len(wv):
            _, j = trees[S.K["wolf"]].query(pos[rv], k=1)
            self.near_wolf[rv] = wv[j]
        elif len(rv):
            self.near_wolf[rv] = -1
        # Тревога сойки слышат все виды рядом.
        at, src = w.alarm_at(pos)
        heard = A & (at > self.alarm_heard) & (t - at < 2.0)
        self.alarm_heard[heard] = at[heard]
        heard &= t - self.ev_t[:, EV_ALARM] > 20
        hi = np.flatnonzero(heard)
        self.alarm_heard[hi] = at[hi]
        self.ev_new[hi, EV_ALARM] = True; self.ev_t[hi, EV_ALARM] = t; self.ev_src[hi] = src[hi]
        self.stats["alarm_heard"] += len(hi)
        # Память о воде: вода в поле зрения.
        cy, cx = w.cell(pos)
        see_w = A & (w.water_dist[cy, cx] < self._rng_vis * 0.7)
        self.mem_water[see_w] = w.water_near[cy[see_w], cx[see_w]]

    # ------------------------------------------------------------------ управление паттернами
    def leader_of(self) -> np.ndarray:
        """Кого сопровождает особь: вожака группы, мать (детёныш) или ближайшего волка (ворон)."""
        lead = np.full(self.cap, -1, np.int64)
        g = self.grp
        m = self.alive & (g >= 0)
        lead[m] = self.g_leader[g[m]]
        lead[lead == np.arange(self.cap)] = -1
        yd = self.year_days
        juv = self.alive & (self.mother >= 0) & (self.age < S.MATURITY[self.sp] * yd * 0.5)
        mo = np.maximum(self.mother, 0)
        juv &= self.alive[mo] & (self.uid[mo] == self.mother_uid)
        lead[juv] = self.mother[juv]
        rv = self.alive & (self.sp == S.K["raven"])
        lead[rv] = self.near_wolf[rv]
        return lead

    def _steer(self):
        A, pos, sp, w, rng = self.alive, self.pos, self.sp, self.world, self.rng
        n = self.cap
        walk = S.WALK[sp] * self.phys[:, 0]
        run = S.RUN[sp] * self.phys[:, 0]
        lead = self.leader_of()
        self._lead = lead
        self._gs = self._gsize()
        pat = self.pattern
        act = pat.copy()
        fm = A & (pat == P["follow"]) & (lead >= 0)
        same = fm & (sp[np.maximum(lead, 0)] == sp)
        la = pat[np.maximum(lead, 0)]
        juv = self.age < S.MATURITY[sp] * self.year_days
        mirror = same & (la != P["follow"]) & ~((la == P["hunt"]) & juv)
        act[mirror] = la[mirror]
        act[fm & ~mirror] = P["follow"]
        hunt_m = mirror & (act == P["hunt"])
        self.target[hunt_m] = self.target[lead[hunt_m]]; self.target_uid[hunt_m] = self.target_uid[lead[hunt_m]]
        flee_m = mirror & (act == P["flee"])
        self.flee_from[flee_m] = self.flee_from[lead[flee_m]]
        act[A & (pat == P["follow"]) & (lead < 0)] = P["explore"]
        self.act = act
        # Направление и скорость по умолчанию: стоять.
        dirv = self.dir.copy()
        spd = np.zeros(n)

        def go(m, target, speed, arrive=2.0):
            v = target[m] - pos[m]
            d = np.linalg.norm(v, axis=1)
            ok = d > arrive
            mm = np.flatnonzero(m)
            dirv[mm[ok]] = v[ok] / d[ok, None]
            spd[mm[ok]] = speed[mm[ok]]
            return mm[~ok]

        def ring(m, field_fn, r):
            pts = pos[m][:, None, :] + r * RING[None]
            return field_fn(pts, m)

        # Сопровождение: далеко от вожака — подтянуться.
        d_lead = np.linalg.norm(pos[np.maximum(lead, 0)] - pos, axis=1)
        far = A & (pat == P["follow"]) & (lead >= 0) & (d_lead > 6 + 2 * np.sqrt(self._gs))
        far &= ~np.isin(act, [P["hunt"], P["flee"]])
        lead_run = self.spd[np.maximum(lead, 0)] > walk * 1.5
        go(far, pos[np.maximum(lead, 0)], np.where(lead_run, run * 0.9, np.where(S.FLYING[sp], run * 0.6, walk * 1.2)))
        near = A & ~far
        # Еда: пастись по градиенту пищи.
        m = near & np.isin(act, [P["graze"]]) | (near & (act == P["follow"]))
        if m.any():
            # Пища здесь и в 24 точках на 8, 25 и 60 м (кольцо со случайным поворотом); сытно здесь — стоять и есть.
            mi = np.flatnonzero(m)
            diet = S.DIET[sp[mi]]
            here = w.food_value(pos[mi], diet)
            ang = rng.random((len(mi), 1)) * np.pi / 4 + np.arange(8) * np.pi / 4
            dirs = np.stack([np.cos(ang), np.sin(ang)], -1)                               # (n, 8, 2)
            pts = pos[mi][:, None, None, :] + np.array([8.0, 25.0, 60.0])[None, :, None, None] * dirs[:, None]
            rv = w.food_value(pts.reshape(-1, 2), np.repeat(diet, 24, 0)).reshape(len(mi), 24) * np.repeat([1.0, 0.8, 0.6], 8)
            best = rv.argmax(1); bv = rv.max(1)
            move = (here < 0.15) & (bv > here + 0.02) & ((act[mi] == P["graze"]) | (self.hunger[mi] > 0.3))   # сопровождающие пасутся рядом
            dirv[mi[move]] = dirs[move, best[move] % 8]
            spd[mi[move]] = walk[mi[move]] * 0.7
            # Память о еде: самое сытное место, замеченное рядом. Скудно вокруг — к нему, иначе уходить прямо.
            rich = bv > 0.3
            bp = pts.reshape(len(mi), 24, 2)[np.arange(len(mi)), best]
            self.mem_food[mi[rich]] = bp[rich]
            poor = (bv < 0.08) & (here < 0.08) & (act[mi] == P["graze"])
            mf = self.mem_food[mi]
            to_mem = poor & ~np.isnan(mf[:, 0]) & (np.linalg.norm(mf - pos[mi], axis=1) > 5)
            mm = np.zeros(n, bool); mm[mi[to_mem]] = True
            go(mm, np.nan_to_num(self.mem_food), walk)
            wander = poor & ~to_mem
            self.mem_food[mi[wander]] = np.nan
            spd[mi[wander]] = walk[mi[wander]]
            dirv[mi[wander]] = self.dir[mi[wander]]
        # Питьё
        m = near & (act == P["drink"])
        if m.any():
            known = m & ~np.isnan(self.mem_water[:, 0])
            go(known, np.nan_to_num(self.mem_water), np.where(S.FLYING[sp], run * 0.5, walk * 1.2), arrive=1.5)
            spd[m & ~known] = walk[m & ~known]
        # Отдых: в нору или в укрытие.
        m = near & (act == P["rest"])
        if m.any():
            den = m & S.DEN[sp]
            go(den, self.home, walk)
            open_ = m & ~S.DEN[sp] & (w.forest_at(pos) < 0.4) & ~S.FLYING[sp]
            if open_.any():
                fv = ring(open_, lambda pts, mm: w.forest_at(pts.reshape(-1, 2)).reshape(-1, 8), 10.0)
                oi = np.flatnonzero(open_)
                dirv[oi] = RING[fv.argmax(1)]; spd[oi] = walk[oi] * 0.6
        # Бегство
        m = A & (act == P["flee"])
        if m.any():
            v = pos[m] - self.flee_from[m]
            d = np.maximum(np.linalg.norm(v, axis=1), 1e-6)
            ang = rng.normal(0, 0.35, m.sum())
            c, s_ = np.cos(ang), np.sin(ang)
            v = v / d[:, None]
            dirv[m] = np.stack([v[:, 0] * c - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c], 1)
            spd[m] = run[m]
        # Разведка
        m = near & np.isin(act, [P["explore"]]) | (A & (act == P["explore"]))
        if m.any():
            ang = rng.normal(0, 0.3, m.sum())
            c, s_ = np.cos(ang), np.sin(ang)
            v = dirv[m]
            dirv[m] = np.stack([v[:, 0] * c - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c], 1)
            spd[m] = np.where(S.FLYING[sp[m]], run[m] * 0.4, walk[m] * 0.8)
        # Падаль
        m = near & (act == P["scavenge"])
        if m.any():
            here = w.carrion[w.cell(pos[m])]
            mi = np.flatnonzero(m)
            eat = here > 0.05
            rest = mi[~eat]
            if len(rest):   # сначала падаль в пределах 15 м (клетки 5 м), иначе запах по грубой сетке
                cy, cx = w.cell(pos[rest])
                fb = np.zeros(len(rest)); fp = np.zeros((len(rest), 2))
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        yy, xx = np.clip(cy + dy, 0, w.n - 1), np.clip(cx + dx, 0, w.n - 1)
                        v = w.carrion[yy, xx]
                        b = v > fb
                        fb[b] = v[b]; fp[b] = np.stack([xx[b] * 5.0 + 2.5, yy[b] * 5.0 + 2.5], 1)
                close = fb > 0.05
                tgt = np.zeros((n, 2)); tgt[rest] = fp
                mm = np.zeros(n, bool); mm[rest[close]] = True
                go(mm, tgt, walk, arrive=0.5)
                rest = rest[~close]
            if len(rest):
                cg = w.carrion_coarse()
                nc = cg.shape[0]
                c = np.clip((pos[rest] / 25.0).astype(int), 0, nc - 1)
                r = np.where(S.FLYING[sp[rest]], 4, 2)
                best_v = np.zeros(len(rest)); best_p = np.zeros((len(rest), 2))
                for dy in range(-4, 5):
                    for dx in range(-4, 5):
                        ok = (np.abs(dy) <= r) & (np.abs(dx) <= r)
                        yy, xx = np.clip(c[:, 1] + dy, 0, nc - 1), np.clip(c[:, 0] + dx, 0, nc - 1)
                        v = np.where(ok, cg[yy, xx], 0)
                        b = v > best_v
                        best_v[b] = v[b]; best_p[b] = np.stack([xx[b] * 25.0 + 12.5, yy[b] * 25.0 + 12.5], 1)
                found = best_v > 0.2
                tgt = np.zeros((n, 2)); tgt[rest] = best_p
                mm = np.zeros(n, bool); mm[rest[found]] = True
                go(mm, tgt, np.where(S.FLYING[sp], run * 0.6, walk * 1.2), arrive=3.0)
                nf = rest[~found]
                spd[nf] = np.where(S.FLYING[sp[nf]], run[nf] * 0.4, walk[nf])
        # Патруль территории
        m = near & (act == P["patrol"])
        if m.any():
            g = self.grp[m]
            ctr = np.where((g >= 0)[:, None], self.g_center[np.maximum(g, 0)] if len(self.g_center) else pos[m], pos[m])
            ang = self.t / 60.0 + self.uid[m] * 0.7
            tgt = np.zeros((n, 2)); tgt[m] = ctr + 0.12 * self.size * np.stack([np.cos(ang), np.sin(ang)], 1)
            go(m, tgt, walk)
        # Проверить источник тревоги
        m = near & (act == P["investigate"])
        if m.any():
            arrived = go(m, self.inv_pt, walk * 0.6, arrive=5.0)
            self.done[arrived] = True
        # Засада: в густой лес и ждать
        m = near & (act == P["ambush"])
        if m.any():
            op = m & (w.forest_at(pos) < 0.5)
            if op.any():
                fv = ring(op, lambda pts, mm: w.forest_at(pts.reshape(-1, 2)).reshape(-1, 8), 10.0)
                oi = np.flatnonzero(op)
                dirv[oi] = RING[fv.argmax(1)]; spd[oi] = walk[oi] * 0.5
            ai = np.flatnonzero(m & (self.prey[:, 0] >= 0) & (self.prey_d[:, 0] < S.CHASE[sp] * 1.5) & (self.hunger > 0.3))
            self._start_hunt(ai, self.prey[ai, 0])
        # Граница мира: разворот к центру.
        edge = A & ((pos < 5) | (pos > self.size - 5)).any(1)
        if edge.any():
            v = self.size / 2 - pos[edge]
            dirv[edge] = v / np.linalg.norm(v, axis=1, keepdims=True)
        # Усталость и детёныши медленнее.
        mul = np.where(self.fatigue > 0.9, 0.7, 1.0) * np.where(juv, 0.6 + 0.4 * self.age / (S.MATURITY[sp] * self.year_days), 1.0)
        self.dir = dirv
        self._want = spd * mul
        # Паттерн «бегство» и «укрытие» заканчиваются, когда угрозы давно нет.
        calm = self.t - self.ev_t[:, EV_THREAT] > 8
        self.done |= A & np.isin(pat, [P["flee"], P["hide"]]) & calm & (self.t - self.pattern_t > 5)
        self.done |= A & (pat == P["investigate"]) & (self.t - self.pattern_t > 20)
        self.done |= A & (pat == P["graze"]) & (self.hunger < 0.08)
        self.done |= A & (pat == P["drink"]) & (self.thirst < 0.05)
        self.done |= A & (pat == P["rest"]) & (self.fatigue < 0.05)
        self.done |= A & (pat == P["scavenge"]) & (self.hunger < 0.1)

    def _gsize(self) -> np.ndarray:
        if not len(self.g_alive):
            return np.ones(self.cap)
        cnt = np.bincount(self.grp[self.alive & (self.grp >= 0)], minlength=len(self.g_alive))
        return np.where(self.grp >= 0, cnt[np.maximum(self.grp, 0)], 1)

    # ------------------------------------------------------------------ потребности
    def _needs(self, dts: float):
        A, sp, act, w = self.alive, self.sp, self.act, self.world
        days = dts / self.day_s
        still = self.spd < 0.3 * S.WALK[sp]
        self.hunger[A] += np.where(S.IS_PRED[sp[A]] | (S.DIET[sp[A], 4] > 0.5), 0.4, 0.5) * days
        self.thirst[A] += S.THIRST[sp[A]] * days
        resting = A & (act == P["rest"]) & still
        self.fatigue += np.where(resting, -3.0, 0.5 + 2.0 * self._running) * days * A
        np.clip(self.fatigue, 0, 1, out=self.fatigue)
        # Еда
        eating = A & np.isin(act, [P["graze"], P["scavenge"], P["follow"]]) & (self.hunger > 0.02) & (self.spd < S.WALK[sp])
        ei = np.flatnonzero(eating)
        if len(ei):
            s = sp[ei]
            amount = S.NEED[s] / (S.EAT_FRAC[s] * self.day_s) * dts
            diet = S.DIET[s].copy()
            diet[act[ei] == P["scavenge"], :4] *= 0.1
            got = w.eat(self.pos[ei], diet, amount)
            self.hunger[ei] -= got / (2 * S.NEED[s])
        # Питьё
        cy, cx = w.cell(self.pos)
        drink = A & (act == P["drink"]) & (w.water_dist[cy, cx] < 3)
        self.thirst[drink] -= 0.2 * dts
        np.clip(self.hunger, 0, 1, out=self.hunger); np.clip(self.thirst, 0, 1, out=self.thirst)
        starving = (self.hunger >= 0.95) * 1.5 + (self.thirst >= 0.95) * 2.0
        fed = (self.hunger < 0.6) & (self.thirst < 0.6)
        self.health += A * days * np.where(starving > 0, -starving, np.where(fed, 0.3, 0.0))
        np.minimum(self.health, 1.0, out=self.health)

    # ------------------------------------------------------------------ триггеры решений
    def _triggers(self):
        A, t = self.alive, self.t
        free = A & (t >= self.lock_until)
        rea = free & ~self.pend_rea & self.ev_new.any(1)
        crit = (t - self.last_decide > 3) & (
            ((self.hunger > 0.6) & ~np.isin(self.act, EAT_ACTS)) |
            ((self.thirst > 0.6) & (self.act != P["drink"]) & (S.THIRST[self.sp] > 0)) |
            ((self.fatigue > 0.8) & (self.act != P["rest"])))
        pat = free & ~self.pend_pat & ~rea & ((t >= self.next_decide) | self.done | crit)
        for e, c in enumerate(self.ev_new[A].sum(0)):
            self.stats["events"][EVENTS[e]] += int(c)
        self.ev_new[:] = False
        ri, pi = np.flatnonzero(rea), np.flatnonzero(pat)
        self.pend_rea[ri] = True; self.pend_pat[pi] = True
        idx = np.concatenate([ri, pi])
        kind = np.concatenate([np.full(len(ri), KIND_REACTION), np.full(len(pi), KIND_PATTERN)])
        if len(idx):
            self.requests.append((idx, kind))

    def take_requests(self) -> tuple[np.ndarray, np.ndarray]:
        """Запросы решений с прошлого вызова: индексы особей и вид запроса (паттерн или реакция)."""
        if not self.requests:
            return np.zeros(0, np.int64), np.zeros(0, np.int64)
        idx = np.concatenate([r[0] for r in self.requests]); kind = np.concatenate([r[1] for r in self.requests])
        self.requests = []
        return idx, kind

    def apply(self, idx: np.ndarray, uid: np.ndarray, kind: np.ndarray, pattern: np.ndarray, target: np.ndarray,
              alarm: np.ndarray, join: np.ndarray, challenge: np.ndarray) -> np.ndarray:
        """Применить решения. pattern = -1 — продолжать прежнее; target — индекс добычи или -1.
        Устаревшие (особь погибла, слот занят другой) пропускаются. Возвращает маску применённых."""
        idx = np.asarray(idx, np.int64)
        ok = self.alive[idx] & (self.uid[idx] == uid)
        rea = kind == KIND_REACTION
        self.pend_rea[idx[rea]] = False; self.pend_pat[idx[~rea]] = False
        i, k, p, tg = idx[ok], kind[ok], pattern[ok], target[ok]
        t = self.t
        locked = t < self.lock_until[i]
        setp = (p >= 0) & ~locked & S.ALLOWED[self.sp[i], np.maximum(p, 0)]
        hunt = setp & (p == P["hunt"])
        tg = np.where(hunt & (tg < 0), self.prey[i, 0], tg)
        bad = hunt & (tg < 0)
        p = np.where(bad, P["explore"], p)
        si = i[setp]
        self.pattern[si] = p[setp]
        self.act[si] = p[setp]
        self.pattern_t[si] = t
        self.done[si] = False
        pk = i[k == KIND_PATTERN]
        self.last_decide[pk] = t
        self.next_decide[pk] = t + (5 + 15 * self.rng.random(len(pk))) * self.interval_mul[pk]
        hi = i[hunt & ~bad]
        self._start_hunt(hi, tg[hunt & ~bad])
        fl = i[setp & (p == P["flee"])]
        self.flee_from[fl] = np.where((self.thr[fl] >= 0)[:, None], self.pos[np.maximum(self.thr[fl], 0)], self.ev_src[fl])
        inv = i[setp & (p == P["investigate"])]
        self.inv_pt[inv] = self.ev_src[inv]
        # Тревога: сойка кричит на весь лес, член группы — своим.
        al = i[alarm[ok]]
        jay = al[self.sp[al] == S.K["jay"]]
        jay = jay[t - self.last_call[jay] > 10]
        for j in jay:
            self.world.raise_alarm(self.pos[j], t)
        self.last_call[jay] = t
        self.stats["alarms"] += len(jay)
        grp_al = al[(self.grp[al] >= 0)]
        if len(grp_al):
            gs = np.unique(self.grp[grp_al])
            mem = np.flatnonzero(self.alive & np.isin(self.grp, gs))
            src = dict(zip(self.grp[grp_al], self.ev_src[grp_al]))
            mem = mem[~np.isin(mem, grp_al)]
            mem = mem[t - self.ev_t[mem, EV_GROUP] > 20]
            self.ev_new[mem, EV_GROUP] = True; self.ev_t[mem, EV_GROUP] = t
            self.ev_src[mem] = np.array([src[g] for g in self.grp[mem]]).reshape(-1, 2)
            self.stats["group_alarms"] += len(gs)
        self.want_join[i[join[ok]]] = t
        self.want_chal[i[challenge[ok]]] = True
        return ok

    # ------------------------------------------------------------------ рефлекс, охота, движение
    def _reflex(self):
        m = self.alive & (self.thr >= 0) & (self.act != P["flee"])
        if not m.any():
            return
        i = np.flatnonzero(m)
        th = self.thr[i]
        ok = self.alive[th]
        d = np.linalg.norm(self.pos[th] - self.pos[i], axis=1)
        jump = ok & (((self.act[th] == P["hunt"]) & (self.spd[th] > 0.4 * S.RUN[self.sp[th]]) & (d < 5)) | (d < 2))
        j = i[jump]
        if len(j):
            self.pattern[j] = P["flee"]; self.act[j] = P["flee"]; self.pattern_t[j] = self.t
            self.flee_from[j] = self.pos[self.thr[j]]
            self.lock_until[j] = self.t + 3.0
            self.dir[j] = self.pos[j] - self.flee_from[j]
            self.dir[j] /= np.maximum(np.linalg.norm(self.dir[j], axis=1, keepdims=True), 1e-6)
            self._want[j] = S.RUN[self.sp[j]] * self.phys[j, 0]
            self.stats["reflexes"] += len(j)

    def _start_hunt(self, i: np.ndarray, tg: np.ndarray):
        if not len(i):
            return
        self.pattern[i] = P["hunt"]; self.act[i] = P["hunt"]
        self.target[i] = tg; self.target_uid[i] = self.uid[tg]
        self.hunt_chase[i] = False; self.hunt_seen[i] = self.t; self.hunt_start[i] = self.t
        self.pattern_t[i] = self.t

    def _end_hunt(self, i: np.ndarray, attempt_failed: np.ndarray):
        own = i[self.pattern[i] == P["hunt"]]
        self.done[own] = True
        self.pattern[own] = P["explore"]; self.act[i] = P["explore"]
        self.target[i] = -1; self.hunt_chase[i] = False

    def _hunt(self):
        h = np.flatnonzero(self.alive & (self.act == P["hunt"]) & (self.target >= 0))
        if not len(h):
            return
        sp, t = self.sp, self.t
        tg = self.target[h]
        valid = self.alive[tg] & (self.uid[tg] == self.target_uid[h])
        v = self.pos[tg] - self.pos[h]
        d = np.linalg.norm(v, axis=1)
        chase = self.hunt_chase[h] | (d < S.CHASE[sp[h]]) | (self.act[tg] == P["flee"]) & (d < 2 * S.CHASE[sp[h]])
        new_chase = chase & ~self.hunt_chase[h] & valid
        own = self.pattern[h] == P["hunt"]
        for s in sp[h[new_chase & own]]:
            self.stats["hunts"][S.KEYS[s]] += 1
        self.hunt_chase[h] = chase
        run = S.RUN[sp[h]] * self.phys[h, 0] * np.where(self.stamina[h] > 0, 1.0, 0.45)
        speed = np.where(chase, run, S.WALK[sp[h]] * 0.8)
        dd = np.maximum(d, 1e-6)
        self.dir[h] = v / dd[:, None]
        self._want[h] = np.where(valid, np.minimum(speed, d / self.dt), 0)
        lost = (t - self.hunt_seen[h] > 4) | (t - self.hunt_start[h] > 120)
        tired = chase & (self.stamina[h] <= 0) & (d > 4)
        caught = valid & (d < 1.5 + 1.0 * S.FLYING[sp[h]])
        caught &= ~(S.FLYING[sp[tg]] & (self.act[tg] == P["flee"]) & ~S.FLYING[sp[h]])   # взлетевшую птицу с земли не поймать
        fail = ~valid | lost | tired
        if fail.any():
            self._end_hunt(h[fail], chase[fail])
        if caught.any():
            hc = h[caught & ~fail]
            prey = self.target[hc]
            strength = S.STRENGTH[sp[hc]] * self.phys[hc, 2] * self.health[hc]
            for q in np.unique(prey):
                hunters = hc[prey == q]
                s_pred = strength[prey == q].sum()
                juv = self.age[q] < S.MATURITY[sp[q]] * self.year_days
                s_prey = S.STRENGTH[sp[q]] * self.phys[q, 2] * self.health[q] * (0.3 if juv else 1.0)
                pk = S.KEYS[sp[hunters[0]]]
                if self.rng.random() < s_pred / (s_pred + s_prey):
                    mass = S.MASS[sp[q]] * (0.3 if juv else 1.0)
                    self.world.add_carrion(self.pos[q][None], mass)
                    self._kill(np.array([q]), "predator:" + pk)
                    self.stats["kills"][pk] += 1
                    self.pattern[hunters[self.pattern[hunters] == P["hunt"]]] = P["scavenge"]
                    self.act[hunters] = P["scavenge"]
                    self.target[hunters] = -1; self.hunt_chase[hunters] = False
                    self.mem_food[hunters] = self.pos[q]
                    self.pattern_t[hunters] = t
                else:
                    self.health[q] -= 0.2
                    self.stamina[q] = min(1.0, self.stamina[q] + 0.3)
                    self.health[hunters] -= 0.05 * S.STRENGTH[sp[q]]
                    self._end_hunt(hunters, np.zeros(len(hunters), bool))
                    if self.health[q] <= 0:
                        self._kill(np.array([q]), "wounds")

    def _move(self):
        A = self.alive
        spd = self._want
        run = S.RUN[self.sp] * self.phys[:, 0]
        # Выносливость: бег тратит, покой восполняет.
        running = A & (spd > 0.6 * run)
        st = S.STAMINA[self.sp] * self.phys[:, 1]
        self.stamina += np.where(running, -self.dt / st, self.dt / (4 * st)) * A
        np.clip(self.stamina, 0, 1, out=self.stamina)
        spd = np.where(running & (self.stamina <= 0), np.minimum(spd, run * 0.45), spd)
        self.spd = spd * A
        self.pos += self.dir * self.spd[:, None] * self.dt
        np.clip(self.pos, 0.5, self.size - 0.5, out=self.pos)

    # ------------------------------------------------------------------ жизнь и смерть
    def _kill(self, i: np.ndarray, cause: str):
        i = i[self.alive[i]]
        if not len(i):
            return
        self.alive[i] = False
        self.spd[i] = 0
        for s in self.sp[i]:
            self.stats["deaths"][(S.KEYS[s], cause)] += 1

    def _life(self, days: float):
        A, sp, yd, t = self.alive, self.sp, self.year_days, self.t
        self.age[A] += days
        old = np.flatnonzero(A & (self.age > self.life))
        self._kill(old, "old_age")
        juv = A & (self.age < S.MATURITY[sp] * yd)
        hz = np.where(juv, S.JUV_MORT[sp], S.ADULT_MORT[sp]) / yd * days
        self._kill(np.flatnonzero(A & (self.rng.random(self.cap) < hz)), "other")
        dead = np.flatnonzero(self.alive & (self.health <= 0))
        if len(dead):
            starve = self.hunger[dead] >= 0.95
            thirst = (self.thirst[dead] >= 0.95) & ~starve
            self._kill(dead[starve], "starvation"); self._kill(dead[thirst], "thirst")
            self._kill(dead[~starve & ~thirst], "wounds")
        A = self.alive
        season = self.season()
        adult = A & (self.age >= S.MATURITY[sp] * yd)
        # Зачатие: самка в сезон гона, рядом (клетка 100 м) взрослый самец своего вида.
        cell = 100.0
        nc = int(np.ceil(self.size / cell))
        c = np.clip((self.pos / cell).astype(np.int64), 0, nc - 1)
        key = sp.astype(np.int64) * nc * nc + c[:, 1] * nc + c[:, 0]
        rep = np.full(S.NS * nc * nc, -1, np.int64)
        males = np.flatnonzero(adult & (self.sex == 1))
        rep[key[males]] = males
        fem = adult & (self.sex == 0) & ~self.pregnant & S.MATE[sp, season] & (self.health > 0.5) & (self.hunger < 0.7)
        fem &= t - self.last_birth > yd / S.BROODS[sp] * self.day_s * 0.8
        fem &= ~(S.TERRITORIAL[sp] & (self.rank > 1))
        fi = np.flatnonzero(fem)
        fa = rep[key[fi]]
        rate = 3.0 / (yd / 4)
        p = 1 - np.exp(-rate * days)
        cap = S.CAP_HA[sp[fi]] * (cell / 100.0) ** 2
        dens = np.bincount(key[A], minlength=S.NS * nc * nc)[key[fi]]
        p = p * np.where(cap > 0, np.clip(1 - dens / np.maximum(cap, 1e-9), 0, 1), 1.0)
        conc = fi[(fa >= 0) & (self.rng.random(len(fi)) < p)]
        fa = rep[key[conc]]
        self.pregnant[conc] = True
        self.due[conc] = t + S.GESTATION[sp[conc]] * yd * self.day_s
        self.father[conc] = np.concatenate([self.traits[fa], self.phys[fa]], 1)
        # Роды
        mothers = np.flatnonzero(A & self.pregnant & (t >= self.due))
        for m in mothers:
            s = sp[m]
            k = int(self.rng.integers(S.LITTER_LO[s], S.LITTER_HI[s] + 1))
            self.give_birth(m, k)

    def give_birth(self, m: int, k: int) -> np.ndarray:
        """Приплод k детёнышей: признаки — среднее родителей с разбросом."""
        s = self.sp[m]
        self.pregnant[m] = False
        self.last_birth[m] = self.t
        mom = np.concatenate([self.traits[m], self.phys[m]])
        mid = (mom + self.father[m]) / 2
        g = mid[None] + self.rng.normal(0, 0.08, (k, 9))
        tr, ph = np.clip(g[:, :5], 0, 1), np.clip(g[:, 5:], 0.7, 1.3)
        ix = self._spawn(np.full(k, s), self.pos[m] + self.rng.normal(0, 1, (k, 2)), np.zeros(k), tr, ph)
        self.mother[ix] = m; self.mother_uid[ix] = self.uid[m]
        self.home[ix] = self.home[m]
        self.mem_water[ix] = self.mem_water[m]
        self.hunger[ix] = 0.1; self.thirst[ix] = 0.1
        self.pattern[ix] = P["follow"]; self.act[ix] = P["follow"]
        self.stats["births"][S.KEYS[s]] += k
        if S.SOCIAL[s]:
            if self.grp[m] >= 0:
                self.grp[ix] = self.grp[m]
            else:
                self._new_group(np.concatenate([[m], ix]))
        return ix

    # ------------------------------------------------------------------ группы
    def _new_group(self, members: np.ndarray, leader: int | None = None) -> int:
        g = len(self.g_alive)
        if leader is None:
            sc = self._score(members)
            leader = members[np.argmax(sc)]
        self.g_alive = np.append(self.g_alive, True); self.g_leader = np.append(self.g_leader, leader)
        self.g_sp = np.append(self.g_sp, self.sp[leader]); self.g_born = np.append(self.g_born, self.t)
        self.g_center = np.vstack([self.g_center, self.pos[leader][None]]); self.g_last_chal = np.append(self.g_last_chal, -1e9)
        self.grp[members] = g
        return g

    def _score(self, i: np.ndarray) -> np.ndarray:
        """Сила в стычке за лидерство: сила, здоровье, властность; детёныши слабее."""
        juv = self.age[i] < S.MATURITY[self.sp[i]] * self.year_days
        return S.STRENGTH[self.sp[i]] * self.phys[i, 2] * self.health[i] * (0.5 + self.traits[i, 3]) * np.where(juv, 0.2, 1.0)

    def _dissolve(self, g: int):
        self.g_alive[g] = False
        self.stats["group_lifetimes"].append((self.t - self.g_born[g]) / self.day_s)
        self.grp[self.grp == g] = -1

    def _groups(self):
        if not len(self.g_alive):
            self._join_solitary()
            return
        A, t, yd = self.alive, self.t, self.year_days
        self.grp[~A] = -1
        cnt = np.bincount(self.grp[A & (self.grp >= 0)], minlength=len(self.g_alive))
        for g in np.flatnonzero(self.g_alive & (cnt <= 1)):
            self._dissolve(g)
        # Вожак погиб — новый вожак сильнейший.
        live = np.flatnonzero(self.g_alive)
        L = self.g_leader[live]
        lost = ~A[L] | (self.grp[L] != live)
        for g in live[lost]:
            mem = np.flatnonzero(A & (self.grp == g))
            self.g_leader[g] = mem[np.argmax(self._score(mem))]
            self.stats["leader_changes"][(S.KEYS[self.g_sp[g]], "death")] += 1
        # Ранги внутри групп
        mem = np.flatnonzero(A & (self.grp >= 0))
        if len(mem):
            o = np.lexsort((-self._score(mem), self.grp[mem]))
            gs = self.grp[mem[o]]
            first = np.r_[0, np.flatnonzero(np.diff(gs)) + 1]
            start = np.repeat(first, np.diff(np.r_[first, len(gs)]))
            self.rank[mem[o]] = np.arange(len(gs)) - start
            self.rank[mem[self.g_leader[self.grp[mem]] == mem]] = 0
        # Вызов вожаку
        ch = np.flatnonzero(A & self.want_chal & (self.grp >= 0))
        self.want_chal[:] = False
        for c in ch:
            g = self.grp[c]; L = self.g_leader[g]
            if L == c or t - self.g_last_chal[g] < 120 or np.linalg.norm(self.pos[c] - self.pos[L]) > 25:
                continue
            self.g_last_chal[g] = t
            self.stats["challenges"] += 1
            sc = self._score(np.array([c, L])) * self.rng.lognormal(0, 0.3, 2)
            win, lose = (c, L) if sc[0] > sc[1] else (L, c)
            self.health[lose] -= self.rng.uniform(0.05, 0.25)
            if win == c:
                self.g_leader[g] = c
                self.stats["leader_changes"][(S.KEYS[self.sp[c]], "challenge")] += 1
            if self.health[lose] <= 0:
                self._kill(np.array([lose]), "fight")
        # Отставшие уходят; перерост — раскол; молодые волки расселяются.
        mem = np.flatnonzero(A & (self.grp >= 0))
        L = self.g_leader[self.grp[mem]]
        far = np.linalg.norm(self.pos[mem] - self.pos[L], axis=1) > 150
        self.grp[mem[far]] = -1
        wolf_disp = mem[(self.sp[mem] == S.K["wolf"]) & (self.rank[mem] > 3) & (self.age[mem] > S.MATURITY[S.K["wolf"]] * yd)]
        leave = wolf_disp[self.rng.random(len(wolf_disp)) < 1.0 / self.day_s]
        self.grp[leave] = -1
        cnt = np.bincount(self.grp[A & (self.grp >= 0)], minlength=len(self.g_alive))
        for g in np.flatnonzero(self.g_alive & (cnt > S.GROUP_MAX[self.g_sp])):
            m = np.flatnonzero(A & (self.grp == g))
            m = m[np.argsort(self.rank[m])]
            out = m[S.GROUP_MAX[self.g_sp[g]]:]
            self.grp[out] = -1
            if len(out) > 1:
                self._new_group(out)
                self.stats["splits"] += 1
        # Слияние стад: вожаки рядом, вместе не больше предела; стаи не сливаются.
        live = np.flatnonzero(self.g_alive)
        cnt = np.bincount(self.grp[A & (self.grp >= 0)], minlength=len(self.g_alive))
        for s in np.unique(self.g_sp[live]):
            if S.TERRITORIAL[s]:
                continue
            gl = live[self.g_sp[live] == s]
            if len(gl) < 2:
                continue
            tree = cKDTree(self.pos[self.g_leader[gl]])
            for a, b in tree.query_pairs(20.0):
                ga, gb = gl[a], gl[b]
                if self.g_alive[ga] and self.g_alive[gb] and cnt[ga] + cnt[gb] <= S.GROUP_MAX[s]:
                    small, big = (ga, gb) if cnt[ga] < cnt[gb] else (gb, ga)
                    self.grp[self.grp == small] = big
                    cnt[big] += cnt[small]
                    self.g_alive[small] = False
                    self.stats["merges"] += 1
        # Территории стай расходятся.
        packs = live[S.TERRITORIAL[self.g_sp[live]] & self.g_alive[live]]
        if len(packs) > 1:
            R = 0.25 * self.size
            ctr = self.g_center[packs]
            for a, b in cKDTree(ctr).query_pairs(R):
                v = ctr[a] - ctr[b]
                v = v / max(np.linalg.norm(v), 1e-6)
                self.g_center[packs[a]] = np.clip(ctr[a] + v * 2, 0, self.size)
                self.g_center[packs[b]] = np.clip(ctr[b] - v * 2, 0, self.size)
        self._join_solitary()

    def _join_solitary(self):
        """Одиночка общественного вида, решивший примкнуть: к группе соседа или вдвоём в новую."""
        A, t = self.alive, self.t
        c = np.flatnonzero(A & (self.grp < 0) & S.SOCIAL[self.sp] & (t - self.want_join < 10) & (self.cons >= 0) & (self.cons_d < 30))
        c = c[self.age[c] >= S.MATURITY[self.sp[c]] * self.year_days * 0.5]
        for i in c:
            j = self.cons[i]
            if not A[j] or self.grp[i] >= 0:
                continue
            g = self.grp[j]
            if g >= 0:
                if (self.grp == g).sum() < S.GROUP_MAX[self.sp[i]]:
                    self.grp[i] = g
                    self.stats["joins"] += 1
            else:
                self._new_group(np.array([i, j]))
                self.stats["joins"] += 1
            self.want_join[i] = -1e9
