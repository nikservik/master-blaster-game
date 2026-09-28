"""Динамика экосистемы по прогонам: численность по видам во времени, причины смерти, охота, группы.

Запуск в WSL: uv run python -m eco.popplot <прогон> [<прогон> ...] --img файл.png. Прогон — папка в ~/ml/out.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--img", required=True)
    a = ap.parse_args()
    reps = {r: json.loads((OUT / r / "report.json").read_text()) for r in a.runs}
    species = [s for s in next(iter(reps.values()))["population"] if s != "day"]
    fig, axes = plt.subplots(1, len(species), figsize=(3.0 * len(species), 2.8), dpi=90)
    for ax, s in zip(axes, species):
        for name, r in reps.items():
            ax.plot(r["population"]["day"], r["population"][s], label=r["variant"])
        ax.set_title(s, fontsize=10); ax.set_xlabel("игровой день"); ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(a.img)
    print("| Прогон | " + " | ".join(f"{s}: старт→итог (мин–макс)" for s in species) + " | Удачных охот волка | Смертей от хищников / голода+жажды / прочее | Групп, размер | Смен вожака |")
    print("|" + "---|" * (len(species) + 5))
    for name, r in reps.items():
        pops = []
        for s in species:
            p = r["population"][s]
            pops.append(f"{p[0]}→{p[-1]} ({min(p)}–{max(p)})")
        pred = starve = other = 0
        for v in r["species"].values():
            for cause, n in v["deaths"].items():
                if cause.startswith("predator"):
                    pred += n
                elif cause in ("hunger", "thirst", "starvation"):
                    starve += n
                else:
                    other += n
        w = r["species"].get("wolf", {})
        g = r["groups"]
        print(f"| {r['variant']} ({r['animals_start']}, {r['sim_days']:.0f} дн.) | " + " | ".join(pops) +
              f" | {w.get('hunt_success') or 0:.0%} | {pred} / {starve} / {other} | {g['mean_count']:.0f}, {g['mean_size']:.1f} | "
              f"{sum(g['leader_changes'].values())} |")


if __name__ == "__main__":
    main()
