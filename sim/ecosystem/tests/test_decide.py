"""Решатели: V0, семплирование, асинхронность, V2–V5, клиент Kev с подменой транспорта, замеры, запись."""
import asyncio
import json

import httpx
import numpy as np

from conftest import make_sim, run
from eco.decide import (Driver, KevOracle, MockOracle, OracleSolver, RandomSolver, UtilitySolver, questions_for,
                        state_text)
from eco.kev import Answer, KevClient
from eco.metrics import Metrics, js_div
from eco.record import Recorder
from eco.sim import KIND_PATTERN, KIND_REACTION
from eco.species import P


def test_v0_hungry_roe_grazes_and_roe_with_wolf_close_flees(sim):
    ids = np.array([sim.add("roe", (100, 100), hunger=0.9, thirst=0.0, fatigue=0.0) for _ in range(50)])
    b = UtilitySolver(0).decide(sim, ids, np.full(50, KIND_PATTERN))
    assert (b.pattern == P["graze"]).mean() > 0.7
    w = sim.add("wolf", (100, 110))
    sim.thr[ids] = w; sim.thr_d[ids] = 10.0
    sim.traits[ids, 0] = 0.1                                          # робкие
    b = UtilitySolver(0).decide(sim, ids, np.full(50, KIND_REACTION))
    assert (b.pattern == P["flee"]).mean() > 0.7


def test_choice_is_sampled_from_distribution_not_argmax(sim):
    i = sim.add("roe", (100, 100))
    s = OracleSolver("V1", MockOracle())
    ans = Answer({"pattern": {"graze": 0.5, "rest": 0.5}}, {}, 0, 0)
    got = {int(s._from_answer(sim, i, int(sim.uid[i]), KIND_PATTERN, ans, {}, "oracle").pattern[0]) for _ in range(100)}
    assert got == {P["graze"], P["rest"]}


def _roe_sees_wolf():
    sim = make_sim()
    roe = sim.add("roe", (100, 100), pattern=P["rest"], next_decide=1e9)
    sim.add("wolf", (100, 112), pattern=P["rest"], next_decide=1e9, hunger=0.0)
    return sim, roe


def test_animal_keeps_pattern_until_answer_arrives_and_late_reaction_is_counted():
    async def go():
        sim, roe = _roe_sees_wolf()
        gate = asyncio.Event()
        solver = OracleSolver("V1", MockOracle(gate=gate))
        m = Metrics(sim, "realtime")
        drv = Driver(sim, solver, "realtime", m)
        for _ in range(3):
            await drv.tick()                  # восприятие: косуля увидела волка — запрос реакции ушёл
        assert sim.pend_rea[roe]
        for _ in range(10):
            await drv.tick()                  # 1 с симуляции без ответа
        assert sim.pend_rea[roe] and sim.pattern[roe] == P["rest"]
        gate.set()
        for _ in range(2):
            await drv.tick()
        assert not sim.pend_rea[roe]
        rep = m.report(sim, solver)
        assert rep["reactions_from_oracle"] == 1 and rep["late_reaction_share"] == 1.0
    asyncio.run(go())


def test_batched_tick_waits_for_answers():
    async def go():
        sim, roe = _roe_sees_wolf()
        drv = Driver(sim, OracleSolver("V1", MockOracle(latency_s=0.01)), "batched")
        for _ in range(3):
            await drv.tick()
        assert not sim.pend_rea[roe] and not drv.inflight
    asyncio.run(go())


def test_v2_leader_asks_oracle_members_follow_without_it(sim):
    ids = [sim.add("roe", (50 + k, 50)) for k in range(3)]
    sim._new_group(np.array(ids), leader=ids[0])
    run(sim, 0.3)
    s = OracleSolver("V2", MockOracle())
    b, asks = s.handle(sim, np.array(ids), np.full(3, KIND_PATTERN))
    assert [a.i for a in asks] == [ids[0]]
    assert sorted(b.idx.tolist()) == ids[1:] and (b.pattern == P["follow"]).all()


def test_v3_cache_hit_on_same_coarse_state(sim):
    a = sim.add("roe", (50, 50), hunger=0.7)
    b = sim.add("roe", (150, 150), hunger=0.72)
    sim.traits[b] = sim.traits[a]; sim.age[b] = sim.age[a]
    o = MockOracle()
    s = OracleSolver("V3", o)
    _, asks = s.handle(sim, np.array([a]), np.array([KIND_PATTERN]))
    assert len(asks) == 1
    s.resolve(sim, asks[0], asyncio.run(o.ask(asks[0].state, asks[0].questions)))
    hit, asks2 = s.handle(sim, np.array([b]), np.array([KIND_PATTERN]))
    assert not asks2 and hit.source == ["cache"]
    assert s.cache_hits == 1 and s.cache_miss == 1


def test_v4_attention_near_asks_mid_uses_cache_far_falls_back(sim):
    near = sim.add("roe", (20, 20)); mid = sim.add("roe", (60, 60)); far = sim.add("roe", (190, 190))
    s = OracleSolver("V4", MockOracle(), observer=(10, 10), near_m=30, far_m=100)
    b, asks = s.handle(sim, np.array([near, mid, far]), np.full(3, KIND_PATTERN))
    assert sorted(a.i for a in asks) == [near, mid]
    assert b.idx.tolist() == [far] and b.source == ["far_v0"]
    assert sim.interval_mul[[near, mid, far]].tolist() == [1.0, 2.0, 4.0]


def test_v5_policy_asked_once_then_sampled_locally(sim):
    i = sim.add("roe", (50, 50), hunger=0.8)
    o = MockOracle()
    s = OracleSolver("V5", o)
    b, asks = s.handle(sim, np.array([i]), np.array([KIND_PATTERN]))
    assert len(b.idx) == 0 and len(asks) == 1
    assert set(asks[0].questions) == {"pattern_calm", "pattern_hungry", "pattern_threat", "pattern_night"}
    got = s.resolve(sim, asks[0], asyncio.run(o.ask(asks[0].state, asks[0].questions)))
    assert got.idx.tolist() == [i] and got.source == ["policy"]
    b2, asks2 = s.handle(sim, np.array([i]), np.array([KIND_PATTERN]))
    assert not asks2 and b2.source == ["policy"] and s.policy_hits == 1


def test_state_is_dense_text_of_100_to_300_tokens_with_2_to_4_questions():
    sim, roe = _roe_sees_wolf()
    run(sim, 0.3)
    text = state_text(sim, roe, KIND_REACTION)
    assert "A wild roe deer" in text and "A wolf is" in text and "Water is" in text
    assert 100 <= len(text) / 4 <= 300
    q, _ = questions_for(sim, roe, KIND_REACTION)
    assert 1 <= len(q) <= 4 and q["reaction"]["type"] == "choice"


def test_kev_solver_posts_state_and_applies_answer():
    posted = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        posted.append(body)
        ans = {}
        for name, q in body["questions"].items():
            if q["type"] == "choice":
                opts = list(q["criteria"])
                pick = "graze" if "graze" in opts else opts[0]
                ans[name] = {"probabilities": {o: float(o == pick) for o in opts}, "choice": pick}
            else:
                ans[name] = {"noul": 0.0}
        return httpx.Response(200, json={"answers": ans, "latency_ms": 7.0})

    async def go():
        sim = make_sim()
        i = sim.add("roe", (50, 50), pattern=P["rest"], next_decide=0.2)
        client = KevClient()
        async with KevOracle(client) as oracle:
            await client._http.aclose()
            client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            m = Metrics(sim, "batched")
            drv = Driver(sim, OracleSolver("V1", oracle), "batched", m)
            for _ in range(3):
                await drv.tick()
        assert posted and posted[0]["state"].startswith("A wild roe deer")
        assert posted[0]["questions"]["pattern"]["instructions"].startswith("You decide what this wild roe deer")
        assert "graze" in posted[0]["questions"]["pattern"]["criteria"]
        assert sim.pattern[i] == P["graze"]
        assert m.model_ms == [7.0]
    asyncio.run(go())


def test_random_solver_and_js_divergence(sim):
    ids = np.array([sim.add("hare", (100, 100)) for _ in range(20)])
    b = RandomSolver(0).decide(sim, ids, np.full(20, KIND_PATTERN))
    assert len(set(b.pattern.tolist())) > 2
    p = np.array([0.5, 0.5, 0.0]); q = np.array([0.0, 0.0, 1.0])
    assert js_div(p, p) == 0.0 and abs(js_div(p, q) - 1.0) < 1e-9


def test_recording_writes_header_and_frames_with_decisions(tmp_path):
    async def go():
        sim, roe = _roe_sees_wolf()
        path = tmp_path / "rec.jsonl"
        rec = Recorder(str(path), sim, every=10)
        drv = Driver(sim, UtilitySolver(0), "batched", Metrics(sim, "batched"), rec)
        for _ in range(30):
            await drv.tick()
        rec.close()
        lines = [json.loads(x) for x in path.read_text().splitlines()]
        assert lines[0]["type"] == "header" and "roe" in [s["key"] for s in lines[0]["species"]]
        frames = lines[1:]
        assert len(frames) == 3 and len(frames[0]["uid"]) == 2
        decs = [d for f in frames for d in f["dec"].values()]
        assert decs and all("chosen" in d for d in decs)
        assert any("reaction" in d or "pattern" in d for d in decs)
    asyncio.run(go())


def test_wolf_burst_scenario_adds_roe_herd_and_hungry_pack():
    from eco.run import add_wolf_burst
    from eco.sim import Sim
    import eco.species as S
    sim = Sim(100, seed=0, species=["roe", "hare", "wolf", "jay"])
    before = sim.count()
    add_wolf_burst(sim, 0)
    after = sim.count()
    assert after[S.K["roe"]] - before[S.K["roe"]] == 20
    assert after[S.K["wolf"]] - before[S.K["wolf"]] == 5


def test_kev_oracle_undoes_server_temperature():
    from eco.decide import sharpen, SHARPEN
    p = sharpen({"a": 0.5, "b": 0.3, "c": 0.2})
    assert abs(sum(p.values()) - 1) < 1e-9
    assert p["a"] > 0.5 and p["c"] < 0.2
    assert abs(p["a"] / p["b"] - (0.5 / 0.3) ** SHARPEN) < 1e-9


def test_v6_late_reaction_falls_back_to_v0_and_late_answer_is_not_applied():
    async def go():
        sim, roe = _roe_sees_wolf()
        gate = asyncio.Event()
        solver = OracleSolver("V6", MockOracle(gate=gate), observer=tuple(sim.pos[roe]))
        m = Metrics(sim, "realtime")
        drv = Driver(sim, solver, "realtime", m)
        for _ in range(3):
            await drv.tick()                  # косуля увидела волка — реакция ушла в Kev
        assert sim.pend_rea[roe]
        for _ in range(5):
            await drv.tick()                  # 0,5 с без ответа — срок 0,3 с прошёл
        assert not sim.pend_rea[roe] and solver.deadline_fallbacks == 1
        gate.set()
        for _ in range(2):
            await drv.tick()
        rep = m.report(sim, solver)
        assert rep["reactions_from_oracle"] == 0 and rep["deadline_fallbacks"] == 1
    asyncio.run(go())


def test_v6_sends_reactions_at_once_and_at_most_12_patterns():
    async def go():
        sim = make_sim()
        ids = [sim.add("roe", (100 + k % 6, 100 + k // 6), next_decide=0.05) for k in range(30)]
        gate = asyncio.Event()
        solver = OracleSolver("V6", MockOracle(gate=gate), observer=(100.0, 100.0))
        drv = Driver(sim, solver, "realtime")
        for _ in range(3):
            await drv.tick()
        patterns = [a for a in drv.inflight if a.kind != KIND_REACTION]
        assert len(patterns) == 12 and len(drv.queue) >= 1
        gate.set()
    asyncio.run(go())
