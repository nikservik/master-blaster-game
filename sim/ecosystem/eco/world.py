"""Мир: сетки 5 м — плотность леса, трава, кустарник, желуди, ягоды, падаль, вода; норы; тревога сойки."""
import numpy as np
from scipy import ndimage

CELL = 5.0            # м, клетка сеток пищи и леса
ALARM_CELL = 20.0     # м, клетка сетки тревоги
CARRION_CELL = 25.0   # м, грубая сетка запаха падали

# Рост по сезонам (весна, лето, осень, зима), доля ёмкости в сутки.
GRASS_R = np.array([0.6, 0.5, 0.2, 0.02])     # доля недостающего до ёмкости, в сутки
SHRUB_R = np.array([0.4, 0.3, 0.15, 0.02])
MAST_DROP = np.array([0.0, 0.0, 0.5, 0.0])      # желуди падают осенью
MAST_DECAY = np.array([0.35, 0.3, 0.02, 0.05])
BERRY_GROW = np.array([0.0, 0.5, 0.3, 0.0])
BERRY_DECAY = np.array([0.3, 0.05, 0.1, 0.5])
CARRION_DECAY = np.array([0.5, 0.8, 0.5, 0.2])


def _smooth_noise(rng: np.random.Generator, h: int, w: int, scale_cells: float) -> np.ndarray:
    z = ndimage.gaussian_filter(rng.random((h, w)), sigma=scale_cells, mode="wrap")
    z -= z.min()
    return z / max(z.max(), 1e-9)


class World:
    def __init__(self, size: float, seed: int, productivity: float = 1.0):
        rng = np.random.default_rng(seed)
        self.size = float(size)
        n = int(round(size / CELL))
        self.n = n
        f = 0.65 * _smooth_noise(rng, n, n, 10) + 0.35 * _smooth_noise(rng, n, n, 3)
        self.forest = np.clip((f - 0.3) / 0.55, 0.0, 1.0)
        # Ручей через весь мир и пруды.
        ys, xs = np.mgrid[0:n, 0:n] * CELL + CELL / 2
        phase = rng.random() * 6.28
        river_y = size * 0.5 + size * 0.15 * np.sin(xs / size * 6.28 * 1.5 + phase)
        water = np.abs(ys - river_y) < 3.0
        for _ in range(max(1, int(size * size / 250.0 ** 2))):
            cx, cy, r = rng.random() * size, rng.random() * size, 6 + rng.random() * 6
            water |= (xs - cx) ** 2 + (ys - cy) ** 2 < r * r
        self.water = water
        dist, (iy, ix) = ndimage.distance_transform_edt(~water, return_indices=True)
        self.water_dist = dist * CELL
        self.water_near = np.stack([ix * CELL + CELL / 2, iy * CELL + CELL / 2], axis=-1)
        self.forest[water] = 0.0
        # Ёмкости пищи, кг на клетку.
        open_ = 1.0 - self.forest
        self.k_grass = 0.9 * productivity * open_ ** 1.5 * ~water
        self.k_shrub = 1.2 * productivity * 4 * self.forest * (1 - self.forest) * ~water
        oak = (_smooth_noise(rng, n, n, 6) > 0.5) & (self.forest > 0.45)
        self.k_mast = 0.6 * productivity * oak * self.forest
        self.k_berry = 0.4 * productivity * (4 * self.forest * (1 - self.forest)) ** 2 * ~water
        self.grass = self.k_grass * 0.6
        self.shrub = self.k_shrub * 0.6
        self.mast = self.k_mast * 0.3
        self.berries = np.zeros_like(self.grass)
        self.carrion = np.zeros_like(self.grass)
        self.foods = [self.grass, self.shrub, self.mast, self.berries, self.carrion]   # порядок как species.FOODS
        # Норы и лёжки — точки в лесу, одна на ~50x50 м.
        cnt = max(4, int(size * size / 2500))
        pts = rng.random((cnt * 4, 2)) * size
        fz = self.forest_at(pts)
        self.dens = pts[np.argsort(-fz + rng.random(len(pts)) * 0.5)[:cnt]]
        na = int(np.ceil(size / ALARM_CELL))
        self.alarm_t = np.full((na, na), -1e9)
        self.alarm_src = np.zeros((na, na, 2))
        self.nc = int(np.ceil(size / CARRION_CELL))

    # --- выборки по позициям ---
    def cell(self, pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        c = np.clip((pos / CELL).astype(np.int64), 0, self.n - 1)
        return c[..., 1], c[..., 0]

    def forest_at(self, pos: np.ndarray) -> np.ndarray:
        iy, ix = self.cell(pos)
        return self.forest[iy, ix]

    def food_value(self, pos: np.ndarray, diet: np.ndarray) -> np.ndarray:
        """Пища по рациону в клетках позиций; diet — (..., 5) веса видов пищи."""
        iy, ix = self.cell(pos)
        return sum(diet[..., f] * self.foods[f][iy, ix] for f in range(5) if diet[..., f].any())

    def carrion_coarse(self) -> np.ndarray:
        n, c = self.n, int(CARRION_CELL / CELL)
        m = (n + c - 1) // c
        pad = np.zeros((m * c, m * c))
        pad[:n, :n] = self.carrion
        return pad.reshape(m, c, m, c).sum(axis=(1, 3))

    # --- изменения ---
    def grow(self, dt_days: float, season: int):
        """Отрастание и порча за dt_days игровых суток."""
        for g, k, r in ((self.grass, self.k_grass, GRASS_R[season]), (self.shrub, self.k_shrub, SHRUB_R[season])):
            if r > 0:
                g += r * dt_days * (k - g)
                np.minimum(g, k, out=g)
        self.mast += MAST_DROP[season] * dt_days * self.k_mast
        self.mast *= 1 - MAST_DECAY[season] * dt_days
        np.minimum(self.mast, self.k_mast * 1.5, out=self.mast)
        self.berries += BERRY_GROW[season] * dt_days * self.k_berry * (1 - self.berries / np.maximum(self.k_berry, 1e-9))
        self.berries *= 1 - BERRY_DECAY[season] * dt_days
        np.maximum(self.berries, 0, out=self.berries)
        self.carrion *= 1 - CARRION_DECAY[season] * dt_days

    def eat(self, pos: np.ndarray, diet: np.ndarray, amount: np.ndarray) -> np.ndarray:
        """Особи в pos съедают до amount кг по рациону diet (N, 5). Возвращает съеденное, кг."""
        iy, ix = self.cell(pos)
        avail = np.stack([self.foods[f][iy, ix] for f in range(5)], axis=1)      # (N, 5)
        w = diet * (avail > 1e-3)
        ws = w.sum(1, keepdims=True)
        want = np.where(ws > 0, amount[:, None] * w / np.maximum(ws, 1e-9), 0.0)
        take = np.minimum(want, avail)
        flat = iy * self.n + ix
        for f in range(5):
            if take[:, f].any():
                g = self.foods[f].reshape(-1)
                np.subtract.at(g, flat, take[:, f])
                np.maximum(g, 0, out=g)
        return take.sum(1)

    def add_carrion(self, pos: np.ndarray, mass: float):
        iy, ix = self.cell(pos)
        self.carrion[iy, ix] += mass

    def raise_alarm(self, pos: np.ndarray, t: float, radius: float = 80.0):
        na = self.alarm_t.shape[0]
        c = (pos / ALARM_CELL).astype(int)
        r = int(np.ceil(radius / ALARM_CELL))
        y0, y1, x0, x1 = max(0, c[1] - r), min(na, c[1] + r + 1), max(0, c[0] - r), min(na, c[0] + r + 1)
        self.alarm_t[y0:y1, x0:x1] = t
        self.alarm_src[y0:y1, x0:x1] = pos

    def alarm_at(self, pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        na = self.alarm_t.shape[0]
        c = np.clip((pos / ALARM_CELL).astype(np.int64), 0, na - 1)
        return self.alarm_t[c[:, 1], c[:, 0]], self.alarm_src[c[:, 1], c[:, 0]]
