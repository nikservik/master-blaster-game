import numpy as np
import pytest

from eco.sim import Sim
from eco.world import CELL


def make_sim(size: float = 200.0, seed: int = 1, **kw) -> Sim:
    """Пустой мир: особей добавляет сам тест (Sim.add)."""
    return Sim(0, seed=seed, size=size, **kw)


def run(sim: Sim, seconds: float):
    for _ in range(int(round(seconds / sim.dt))):
        sim.step()


def grass_spot(sim: Sim) -> np.ndarray:
    """Центр клетки с самой густой травой."""
    iy, ix = np.unravel_index(np.argmax(sim.world.k_grass), sim.world.k_grass.shape)
    return np.array([ix * CELL + CELL / 2, iy * CELL + CELL / 2])


@pytest.fixture
def sim() -> Sim:
    return make_sim()
