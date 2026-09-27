"""Сводка серии прогонов sweep.sh: таблица Markdown и графики PNG.

Запуск в WSL: uv run python -m eco.summary <серия> [<серия> ...] [--img каталог]. Читает ~/ml/out/<серия>_*/report.json.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "out"
VARIANTS = ["V0", "V1", "V2", "V3", "V4", "V5"]


def load(series: str) -> list[dict]:
    reps = []
    for p in sorted(OUT.glob(f"{series}_*/report.json")):
        r = json.loads(p.read_text())
        r["_name"] = p.parent.name[len(series) + 1:]
        reps.append(r)
    return reps


def species_mean(r: dict, key: str) -> float | None:
    vals = [v[key] for v in r["species"].values() if v.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def fmt(v, spec=".2f"):
    return "—" if v is None else format(v, spec)


def row(r: dict) -> str:
    d = r["decisions"]
    lat = r["latency_ms"]
    extra = []
    if "cache" in r:
        extra.append(f"кэш {r['cache']['hit_rate'] or 0:.0%}")
    if "policy" in r:
        extra.append(f"из политики {r['policy']['hits']}")
    if "attention_tiers" in r:
        extra.append(f"внимание {r['attention_tiers']}")
    return (f"| {r['_name']} | {r['variant']} | {r['animals_start']} | {r['sim_days']:.2f} | {r['game_days_per_wall_min']:.3f} | "
            f"{d['requested_per_sim_s']:.0f} | {d['oracle_asks']} | {d['asks_per_wall_s']:.0f} | "
            f"{fmt(lat['model']['p50'], '.0f')}/{fmt(lat['model']['p95'], '.0f')} | "
            f"{fmt(lat['road']['p50'], '.0f')}/{fmt(lat['road']['p95'], '.0f')} | {fmt(r['late_reaction_share'], '.0%')} | "
            f"{fmt(species_mean(r, 'choice_entropy_bits'))} | {fmt(species_mean(r, 'js_bold_vs_timid_bits'), '.3f')} | "
            f"{fmt((r.get('gpu') or {}).get('vram_mb_max'), '.0f')} | {', '.join(extra)} |")


HEAD = ("| Прогон | Вариант | Животных | Игр. дней | Дней/мин | Решений/с сим. | К Kev | К Kev/с стены | Модель p50/p95 | "
        "С дороги p50/p95 | Опоздало | Энтропия | JS хар. | VRAM, МБ | Прочее |\n|" + "---|" * 15)


def plots(reps: list[dict], img: Path, prefix: str):
    img.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), dpi=90)
    for v in VARIANTS:
        rs = sorted([r for r in reps if r["variant"] == v], key=lambda r: r["animals_start"])
        if not rs:
            continue
        n = [r["animals_start"] for r in rs]
        ax[0].plot(n, [r["game_days_per_wall_min"] for r in rs], "o-", label=v)
        ax[1].plot(n, [max(r["decisions"]["asks_per_wall_s"], 0.1) for r in rs], "o-", label=v)
    for a, t in zip(ax, ["Игровых дней за минуту", "Запросов к Kev в секунду"]):
        a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("животных"); a.set_title(t, fontsize=10); a.grid(alpha=0.3)
    ax[0].axhline(60 / 600, color="gray", lw=0.8, ls="--")   # реальное время: сутки 600 с → 0,1 дня/мин
    ax[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(img / f"{prefix}_scale.png")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series", nargs="+")
    ap.add_argument("--img", default=None)
    a = ap.parse_args()
    for s in a.series:
        reps = load(s)
        print(f"\n### {s}\n\n{HEAD}")
        for r in reps:
            print(row(r))
        if a.img:
            plots(reps, Path(a.img), s)


if __name__ == "__main__":
    main()
