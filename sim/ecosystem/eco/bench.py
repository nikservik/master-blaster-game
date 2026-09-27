"""Замер E0: задержка и пропускная способность Kev при разном числе одновременных запросов, размере state и числе вопросов.

Запуск в WSL: uv run python -m eco.bench [--label имя] [--per 200]. Результат — sim/out/e0_<label>.json.
State у каждого запроса свой (случайные числа), чтобы кэш префикса не делал замер быстрее, чем в симуляции.
"""
import argparse
import asyncio
import json
import random
import statistics
import subprocess
import threading
import time
from pathlib import Path

from eco.kev import KevClient

OUT = Path(__file__).resolve().parents[2] / "out"

PATTERNS = {
    "graze": "eat grass or shrubs where you are",
    "drink": "walk to the nearest known water and drink",
    "rest": "lie down in cover and rest",
    "follow": "follow the group leader",
    "flee": "run away from the threat",
    "hide": "freeze or hide in dense cover",
    "scout": "walk out to look around carefully",
}
QUESTION_SETS = [
    {"pattern": {"type": "choice", "criteria": PATTERNS}},
    {"alarm": {"type": "noul", "instructions": "Should the animal call an alarm to its group now?"}},
    {"target": {"type": "choice", "criteria": {f"deer_{i}": f"deer at {random.randint(10, 80)} m" for i in range(4)}}},
    {"approach": {"type": "noul", "instructions": "Should the animal approach the noise to look?"}},
    {"leave_group": {"type": "noul", "instructions": "Should the animal leave its group?"}},
    {"challenge": {"type": "noul", "instructions": "Should the animal challenge the group leader?"}},
]


def make_state(rng: random.Random, target_tokens: int) -> str:
    """Плотный state косули; строки добавляются, пока не наберётся примерно target_tokens (4 символа на токен)."""
    lines = [
        "species: roe deer", f"age: {rng.randint(1, 9)} years", f"sex: {rng.choice(['female', 'male'])}",
        f"hunger: {rng.random():.2f}", f"thirst: {rng.random():.2f}", f"fatigue: {rng.random():.2f}",
        f"health: {rng.random():.2f}", f"boldness: {rng.random():.2f}", f"vigilance: {rng.random():.2f}",
        f"sociability: {rng.random():.2f}", f"time: {rng.choice(['dawn', 'day', 'dusk', 'night'])}",
        f"current pattern: {rng.choice(list(PATTERNS))}",
    ]
    kinds = ["wolf", "lynx", "fox", "roe deer", "hare", "jay", "boar"]
    i = 0
    while sum(len(s) + 1 for s in lines) < target_tokens * 4:
        lines.append(f"sees {rng.choice(kinds)}: {rng.randint(5, 150)} m {rng.choice(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'])}, "
                     f"{rng.choice(['moving', 'still', 'running'])}, visibility {rng.random():.1f}")
        i += 1
        if i % 3 == 0:
            lines.append(f"remembers water {rng.randint(20, 400)} m {rng.choice(['N', 'E', 'S', 'W'])}")
    return "\n".join(lines)


class GpuSampler:
    """Опрашивает nvidia-smi раз в 0,5 с: загрузка GPU и занятая видеопамять."""
    def __init__(self):
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip().split(",")
                self.samples.append((float(out[0]), float(out[1])))
            except Exception:
                pass
            self._stop.wait(0.5)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


async def run_config(client: KevClient, concurrency: int, tokens: int, n_questions: int, total: int, seed: int) -> dict:
    rng = random.Random(seed)
    questions = {}
    for q in QUESTION_SETS[:n_questions]:
        questions.update(q)
    states = [make_state(rng, tokens) for _ in range(total)]
    sem = asyncio.Semaphore(concurrency)
    answers = []

    async def one(state):
        async with sem:
            answers.append(await client.ask(state, questions))

    start = time.perf_counter()
    with GpuSampler() as gpu:
        await asyncio.gather(*(one(s) for s in states))
    wall = time.perf_counter() - start
    model = [a.model_ms for a in answers]
    road = [a.total_ms for a in answers]
    return {
        "concurrency": concurrency, "state_tokens": tokens, "questions": n_questions, "requests": total,
        "req_per_s": total / wall, "decisions_per_s": total * n_questions / wall,
        "model_ms": {"p50": pct(model, 50), "p95": pct(model, 95), "p99": pct(model, 99)},
        "road_ms": {"p50": pct(road, 50), "p95": pct(road, 95), "p99": pct(road, 99), "mean": statistics.mean(road)},
        "late_300ms": sum(1 for r in road if r > 300) / total,
        "gpu_util_mean": statistics.mean([g for g, _ in gpu.samples]) if gpu.samples else None,
        "vram_mb_max": max([m for _, m in gpu.samples]) if gpu.samples else None,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="base")
    ap.add_argument("--per", type=int, default=8, help="запросов на одного одновременного клиента в каждой конфигурации")
    ap.add_argument("--concurrency", default="1,8,32,64")
    ap.add_argument("--tokens", default="100,200,400")
    ap.add_argument("--questions", default="1,3,6")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    async with KevClient(concurrency=256) as client:
        await client.ask(make_state(random.Random(0), 100), QUESTION_SETS[0])   # прогрев
        for c in map(int, args.concurrency.split(",")):
            for t in map(int, args.tokens.split(",")):
                for q in map(int, args.questions.split(",")):
                    total = max(32, c * args.per)
                    r = await run_config(client, c, t, q, total, seed=c * 1000 + t + q)
                    results.append(r)
                    print(f"c={c:3d} tok={t} q={q} req/s={r['req_per_s']:7.1f} model p50/p95={r['model_ms']['p50']:.0f}/{r['model_ms']['p95']:.0f} "
                          f"road p50/p95/p99={r['road_ms']['p50']:.0f}/{r['road_ms']['p95']:.0f}/{r['road_ms']['p99']:.0f} "
                          f"late={r['late_300ms']:.2f} gpu={r['gpu_util_mean']} vram={r['vram_mb_max']}", flush=True)
    (OUT / f"e0_{args.label}.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
