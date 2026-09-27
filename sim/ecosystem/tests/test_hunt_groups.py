"""Охота, рефлекс, падаль, группы и лидерство, межвидовое."""
import numpy as np

from conftest import make_sim, run
from eco.species import P


def test_wolf_catches_exhausted_fawn_and_leaves_carcass(sim):
    fawn = sim.add("roe", (100, 100), age_years=0.1, stamina=0.0, health=0.3, next_decide=1e9)
    w = sim.add("wolf", (100, 108), next_decide=1e9, hunger=0.7)
    sim._start_hunt(np.array([w]), np.array([fawn]))
    run(sim, 10)
    assert not sim.alive[fawn]
    assert sim.stats["deaths"][("roe", "predator:wolf")] == 1
    assert sim.stats["kills"]["wolf"] == 1 and sim.stats["hunts"]["wolf"] == 1
    assert sim.world.carrion.sum() > 0
    run(sim, 10)
    assert sim.hunger[w] < 0.7                      # ест добычу


def test_exhausted_wolf_gives_up_the_chase(sim):
    hare = sim.add("hare", (100, 60), pattern=P["flee"], next_decide=1e9, lock_until=1e9)
    sim.flee_from[hare] = (100, 0)
    w = sim.add("wolf", (100, 20), next_decide=1e9, stamina=0.05)
    sim._start_hunt(np.array([w]), np.array([hare]))
    run(sim, 8)
    assert sim.alive[hare]
    assert sim.pattern[w] != P["hunt"] and sim.target[w] == -1


def test_reflex_flee_when_predator_jumps_closer_than_5_m(sim):
    roe = sim.add("roe", (100, 100), next_decide=1e9, pattern=P["graze"])
    w = sim.add("wolf", (100, 104), next_decide=1e9)
    sim._start_hunt(np.array([w]), np.array([roe]))
    sim.hunt_chase[w] = True
    run(sim, 0.3)                                   # один шаг восприятия
    assert sim.pattern[roe] == P["flee"]
    assert sim.lock_until[roe] > sim.t
    assert sim.stats["reflexes"] >= 1


def _herd(sim, n, pos, strength=None):
    ids = [sim.add("roe", np.array(pos) + [k, 0], next_decide=1e9, pattern=P["follow"]) for k in range(n)]
    g = sim._new_group(np.array(ids), leader=ids[0])
    return ids, g


def test_new_leader_after_leader_death(sim):
    ids, g = _herd(sim, 4, (50, 50))
    sim.phys[ids[2], 2] = 1.3; sim.traits[ids[2], 3] = 1.0
    sim._kill(np.array([ids[0]]), "predator:wolf")
    run(sim, 1.0)
    assert sim.g_leader[g] == ids[2]
    assert sim.stats["leader_changes"][("roe", "death")] == 1


def test_challenge_outcome_by_strength(sim):
    ids, g = _herd(sim, 3, (50, 50))
    sim.health[ids[0]] = 0.2; sim.traits[ids[0], 3] = 0.0
    sim.phys[ids[1], 2] = 1.3; sim.traits[ids[1], 3] = 1.0
    sim.want_chal[ids[1]] = True
    run(sim, 1.0)
    assert sim.g_leader[g] == ids[1]
    assert sim.stats["leader_changes"][("roe", "challenge")] == 1


def test_solitary_joins_nearby_group_when_decided(sim):
    ids, g = _herd(sim, 3, (50, 50))
    lone = sim.add("roe", (60, 52), next_decide=1e9)
    run(sim, 0.3)                                   # восприятие: ближайший сородич
    sim.want_join[lone] = sim.t
    run(sim, 1.0)
    assert sim.grp[lone] == g


def test_oversized_herd_splits_and_close_herds_merge(sim):
    ids, g = _herd(sim, 9, (50, 50))                # предел косули — 6
    run(sim, 1.0)
    groups = {int(sim.grp[i]) for i in ids}
    assert len(groups) == 2 and sim.stats["splits"] == 1
    s2 = make_sim()
    a, ga = _herd(s2, 2, (50, 50))
    b, gb = _herd(s2, 2, (58, 50))
    run(s2, 1.0)
    assert s2.grp[a[0]] == s2.grp[b[0]] and s2.stats["merges"] == 1


def test_jay_alarm_is_heard_by_all_species_nearby(sim):
    jay = sim.add("jay", (40, 40), next_decide=1e9)
    roe = sim.add("roe", (70, 40), next_decide=1e9)
    hare = sim.add("hare", (50, 60), next_decide=1e9)
    far = sim.add("roe", (190, 190), next_decide=1e9)
    sim.apply(np.array([jay]), sim.uid[[jay]], np.array([1]), np.array([-1]), np.array([-1]),
              np.array([True]), np.array([False]), np.array([False]))
    run(sim, 0.3)
    assert sim.stats["alarms"] == 1
    idx, kind = sim.take_requests()
    assert {roe, hare} <= set(idx[kind == 1].tolist())
    assert far not in idx[kind == 1]


def test_raven_follows_wolves_and_fox_eats_carrion(sim):
    w = sim.add("wolf", (150, 150), next_decide=1e9, pattern=P["rest"])
    r = sim.add("raven", (30, 30), next_decide=1e9, pattern=P["follow"])
    d0 = np.linalg.norm(sim.pos[r] - sim.pos[w])
    run(sim, 8)
    assert np.linalg.norm(sim.pos[r] - sim.pos[w]) < d0 - 30
    sim.world.add_carrion(np.array([[60.0, 60.0]]), 10.0)
    fox = sim.add("fox", (62, 66), next_decide=1e9, pattern=P["scavenge"], hunger=0.8)
    run(sim, 20)
    assert sim.hunger[fox] < 0.5
