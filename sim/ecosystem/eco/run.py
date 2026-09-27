"""Прогон экосистемы: python -m eco.run --variant V0 --animals 1000 --days 30 ...

Итог — ~/ml/out/<run>/report.json (путь: --out); запись для просмотрщика — --record <файл.jsonl>.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

import numpy as np

from eco import species as S
from eco.decide import Driver, KevOracle, MockOracle, make_solver
from eco.metrics import Metrics
from eco.record import Recorder
from eco.sim import Sim

OUT = Path.home() / "ml" / "out"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Лесная экосистема с решениями Kev")
    ap.add_argument("--variant", default="V0", choices=["random", "V0", "V1", "V2", "V3", "V4", "V5"])
    ap.add_argument("--oracle", default="mock", choices=["mock", "kev"])
    ap.add_argument("--animals", type=int, default=1000)
    ap.add_argument("--days", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--time", default="batched", choices=["batched", "realtime"])
    ap.add_argument("--species", default="base", help="base | all | список через запятую: roe,hare,wolf,jay")
    ap.add_argument("--record", default=None, help="путь JSONL для просмотрщика")
    ap.add_argument("--record-every", type=int, default=10, help="кадр раз в N тактов")
    ap.add_argument("--observer", default=None, help="x,y — точка камеры для V4 (по умолчанию центр мира)")
    ap.add_argument("--size", type=float, default=None, help="сторона мира, м (по умолчанию 500 м на 1000 животных)")
    ap.add_argument("--day-seconds", type=float, default=600.0)
    ap.add_argument("--year-days", type=float, default=12.0)
    ap.add_argument("--productivity", type=float, default=1.0)
    ap.add_argument("--mock-latency", type=float, default=0.0, help="задержка MockOracle, с")
    ap.add_argument("--run", default=None, help="имя прогона (папка в --out)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--scenario", default=None, choices=["wolves"],
                    help="wolves — всплеск: к 20 косулям у центра выходит голодная стая из 5 волков в 60 м")
    return ap.parse_args(argv)


def species_list(arg: str) -> list[str]:
    if arg == "base":
        return list(S.BASE)
    if arg == "all":
        return list(S.KEYS)
    return arg.split(",")


def add_wolf_burst(sim: Sim, seed: int):
    """Всплеск E4: 20 косуль пасутся у центра мира, в 60 м к востоку — голодная стая из 5 волков."""
    rng = np.random.default_rng(seed)
    c = np.array([sim.size / 2, sim.size / 2])
    for _ in range(20):
        sim.add("roe", c + rng.normal(0, 8, 2))
    for _ in range(5):
        sim.add("wolf", c + np.array([60.0, 0.0]) + rng.normal(0, 4, 2), hunger=0.9)



async def main_async(a) -> dict:
    sim = Sim(a.animals, seed=a.seed, species=species_list(a.species), size=a.size, day_seconds=a.day_seconds,
              year_days=a.year_days, productivity=a.productivity)
    if a.scenario == "wolves":
        add_wolf_burst(sim, a.seed)
    observer = tuple(map(float, a.observer.split(","))) if a.observer else (sim.size / 2, sim.size / 2)
    oracle = None
    if a.variant not in ("random", "V0"):
        oracle = KevOracle() if a.oracle == "kev" else MockOracle(a.mock_latency, a.seed)
    solver = make_solver(a.variant, oracle, a.seed, observer)
    name = a.run or f"{a.variant}_{a.oracle if oracle else 'none'}_{a.animals}_{a.time}_s{a.seed}_{time.strftime('%m%d-%H%M%S')}"
    out = Path(a.out) / name
    out.mkdir(parents=True, exist_ok=True)
    metrics = Metrics(sim, a.time)
    metrics.sample(sim)
    rec = Recorder(a.record, sim, a.record_every) if a.record else None
    drv = Driver(sim, solver, a.time, metrics, rec)
    wall0 = time.perf_counter()

    def on_day(s: Sim):
        if not a.quiet:
            c = s.count()
            pops = " ".join(f"{S.KEYS[i]}={c[i]}" for i in s.species)
            print(f"day {s.day:5.1f} {S.SEASONS[s.season()]:6s} wall {time.perf_counter() - wall0:7.1f}s  {pops}", flush=True)

    gpu = None
    extra = {"args": vars(a), "run": name}
    if oracle is not None:
        async with oracle:
            if a.oracle == "kev":
                from eco.bench import GpuSampler
                gpu = GpuSampler()
                gpu.__enter__()
            try:
                await drv.run(a.days, realtime=a.time == "realtime", on_day=on_day)
            finally:
                if gpu:
                    gpu.__exit__()
        extra["oracle_errors"] = drv.errors
        if gpu and gpu.samples:
            extra["gpu"] = {"util_mean": float(np.mean([g for g, _ in gpu.samples])),
                            "vram_mb_max": float(max(m for _, m in gpu.samples))}
    else:
        await drv.run(a.days, realtime=a.time == "realtime", on_day=on_day)
    if rec:
        rec.close()
    rep = metrics.report(sim, solver, extra)
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    if not a.quiet:
        summary(rep, out)
    return rep


def summary(rep: dict, out: Path):
    print(f"\n== {rep['run']}: {rep['sim_days']:.1f} игровых дней за {rep['wall_s']:.0f} с стены, "
          f"{rep['game_days_per_wall_min']:.2f} дня/мин, животных {rep['animals_final']}")
    d = rep["decisions"]
    print(f"решений: запрошено {d['requested']}, обслужено {d['served']}, к оракулу {d['oracle_asks']} "
          f"({d['asks_per_wall_s']:.1f}/с стены)")
    lat = rep["latency_ms"]
    if lat["road"]["p50"] is not None:
        print(f"задержка мс: модель p50/p95/p99 {lat['model']}, с дороги {lat['road']}, опоздавших реакций {rep['late_reaction_share']}")
    for k, v in rep["species"].items():
        print(f"  {k:6s} итог {v['final']:5d}  рождено {v['births']:5d}  смерти {v['deaths']}  "
              f"охота {v['kills']}/{v['hunts']}  энтропия {v['choice_entropy_bits'] or 0:.2f}  JS {v['js_bold_vs_timid_bits']}")
    g = rep["groups"]
    print(f"события: {rep['events']}, тревоги: {rep['alarms']}, рефлексов {rep['reflexes']}")
    print(f"группы: {g['mean_count']:.0f} шт, размер {g['mean_size']:.1f}, смен лидера {g['leader_changes']}")
    for k, name in (("cache", "кэш"), ("attention_tiers", "внимание"), ("policy", "политика")):
        if k in rep:
            print(f"{name}: {rep[k]}")
    print(f"отчёт: {out / 'report.json'}")


def main(argv=None):
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    main()
