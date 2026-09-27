"""Векторная механика: голод и еда, питьё, смерти, зачатие, роды и наследование."""
import numpy as np

from conftest import grass_spot, make_sim, run
from eco import species as S
from eco.species import P


def test_hunger_rises_without_food_and_falls_when_grazing(sim):
    spot = grass_spot(sim)
    sim.world.grass[:] = sim.world.k_grass
    fed = sim.add("roe", spot, hunger=0.7, pattern=P["graze"], next_decide=1e9)
    starving = sim.add("roe", spot + [0.3, 0], hunger=0.7, pattern=P["rest"], next_decide=1e9)
    run(sim, 60)
    assert sim.hunger[fed] < 0.55
    assert sim.hunger[starving] > 0.7


def test_animal_walks_to_known_water_and_drinks(sim):
    near = sim.world.water_near[20, 20]
    i = sim.add("roe", near + [0, 25], thirst=0.8, pattern=P["drink"], next_decide=1e9)
    sim.mem_water[i] = near
    run(sim, 60)
    assert sim.thirst[i] < 0.3


def test_deaths_by_cause_are_counted(sim):
    a = sim.add("roe", (50, 50), hunger=1.0, health=0.001, next_decide=1e9)
    b = sim.add("hare", (60, 60), thirst=1.0, health=0.001, next_decide=1e9)
    c = sim.add("jay", (70, 70), next_decide=1e9)
    sim.age[c] = sim.life[c] + 1
    run(sim, 1.0)
    assert not sim.alive[[a, b, c]].any()
    d = sim.stats["deaths"]
    assert d[("roe", "starvation")] == 1 and d[("hare", "thirst")] == 1 and d[("jay", "old_age")] == 1


def test_female_conceives_in_rut_when_male_is_near():
    sim = make_sim(year_days=12)
    sim.t = sim.day_s * 3.5                       # лето — гон косули
    f = sim.add("roe", (50, 50), sex=0, next_decide=1e9)
    sim.add("roe", (60, 55), sex=1, next_decide=1e9)
    lone = sim.add("roe", (180, 180), sex=0, next_decide=1e9)
    for _ in range(1000):
        sim._life(0.01)
    assert sim.pregnant[f]
    assert not sim.pregnant[lone]
    assert sim.due[f] > sim.t


def test_litter_inherits_parents_traits_with_spread(sim):
    m = sim.add("roe", (50, 50), sex=0)
    sim.traits[m] = 0.0
    sim.father[m] = np.r_[np.ones(5), np.ones(4)]
    sim.phys[m] = 1.0
    kids = sim.give_birth(m, 2)
    assert len(kids) == 2
    assert np.all(np.abs(sim.traits[kids] - 0.5) < 0.35)
    assert (sim.mother[kids] == m).all() and (sim.pattern[kids] == P["follow"]).all()
    assert sim.grp[kids[0]] >= 0 and sim.grp[kids[0]] == sim.grp[m]      # косуля — стадный вид
    assert sim.stats["births"]["roe"] == 2


def test_pregnancy_ends_with_litter_in_species_range(sim):
    m = sim.add("hare", (50, 50), sex=0, pregnant=True, due=0.5)
    n0 = sim.alive.sum()
    run(sim, 1.0)
    born = sim.alive.sum() - n0
    assert S.LITTER_LO[S.K["hare"]] <= born <= S.LITTER_HI[S.K["hare"]]
    assert not sim.pregnant[m]


def test_grass_regrows_by_season(sim):
    sim.world.grass[:] = 0
    sim.world.grow(0.5, season=0)
    spring = sim.world.grass.sum()
    sim.world.grass[:] = 0
    sim.world.grow(0.5, season=3)
    assert spring > 5 * sim.world.grass.sum()
