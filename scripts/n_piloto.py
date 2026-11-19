#!/usr/bin/env python3
"""Calcula o N da coleta completa a partir do piloto (issue #4).

Critério: precisão. Para cada célula (projeto × gerenciador × cenário) e métrica,
N é o menor n tal que a meia-largura do IC 95% da média fique dentro de ±E da
média ou de um piso absoluto, o que for maior:

    t(0.975, n−1) · DP / √n ≤ max(E · média, piso)

O piso evita exigir precisão sem relevância prática em execuções muito curtas
(±5% de 0,05 s = ±2,5 ms). Padrões: E = 5%, piso = 0,1 s (tempos) e 10 MB (memória).

O N da coleta é o maior N entre as células para a métrica principal (M1), com o
mínimo definido no design (30). Também estima a duração da coleta.

Uso:
  mise exec -- python scripts/n_piloto.py data/piloto [--margem 0.05] [--piso-s 0.1] [--piso-mb 10]
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics as st
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Quantis t(0.975, gl) — tabela padrão; acima de 120 gl usa-se a normal (1.96)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
        23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
        30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t975(df: int) -> float:
    if df in T975:
        return T975[df]
    if df > 120:
        return 1.960
    # interpola entre as entradas tabeladas mais próximas
    lo = max(k for k in T975 if k < df)
    hi = min(k for k in T975 if k > df)
    return T975[lo] + (T975[hi] - T975[lo]) * (df - lo) / (hi - lo)


def n_needed(mean: float, sd: float, margin: float, floor: float = 0.0, cap: int = 10_000) -> int:
    """Menor n com t(0.975, n−1)·sd/√n ≤ max(margin·média, piso absoluto)."""
    target = max(margin * mean, floor)
    if target <= 0:
        return cap
    for n in range(2, cap + 1):
        if t975(n - 1) * sd / math.sqrt(n) <= target:
            return n
    return cap


def quartiles(xs: list[float]) -> tuple[float, float]:
    q = st.quantiles(xs, n=4, method="inclusive")
    return q[0], q[2]


METRICS = {"wall_s": ("M1 tempo de parede", "s"), "cpu_s": ("M2 tempo de CPU", "s"),
           "maxrss_mb": ("M5 pico de memória", "MB")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", help="pasta com runs.csv do piloto")
    ap.add_argument("--margem", type=float, default=0.05, help="E: meia-largura relativa do IC 95%% (padrão 0.05)")
    ap.add_argument("--minimo", type=int, default=30, help="N mínimo (padrão 30, docs/02 §2.5)")
    ap.add_argument("--piso-s", type=float, default=0.1,
                    help="piso absoluto da margem para tempos, em s (padrão 0.1; 0 = só relativo)")
    ap.add_argument("--piso-mb", type=float, default=10.0,
                    help="piso absoluto da margem para memória, em MB (padrão 10; 0 = só relativo)")
    args = ap.parse_args()

    folder = Path(args.pasta)
    rows = list(csv.DictReader(open(folder / "runs.csv")))
    ok = [r for r in rows if r["exit_code"] == "0"]
    failed = len(rows) - len(ok)

    cells: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in ok:
        key = (r["project"], r["pm"], r["scenario"])
        for m in METRICS:
            cells[key][m].append(float(r[m]))

    out: list[str] = []
    out.append(f"# Resumo do piloto — {folder}\n")
    piso = ""
    if args.piso_s or args.piso_mb:
        piso = f" ou ±{args.piso_s:g} s / ±{args.piso_mb:g} MB, o que for maior"
    out.append(f"Execuções: {len(rows)} ({failed} com falha na instalação). "
               f"Critério: IC 95% da média com meia-largura ≤ ±{args.margem:.0%} da média{piso}; "
               f"mínimo N = {args.minimo}.\n")

    need: dict[str, list[tuple[int, tuple]]] = defaultdict(list)
    for m, (label, unit) in METRICS.items():
        out.append(f"\n## {label} ({unit})\n")
        out.append("| Projeto | Gerenciador | Cenário | n | Média | Mediana | IQR | DP | CV | N necessário |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for key in sorted(cells):
            xs = cells[key][m]
            if len(xs) < 2:
                continue
            mean, sd, med = st.mean(xs), st.stdev(xs), st.median(xs)
            q1, q3 = quartiles(xs)
            cv = sd / mean if mean else float("inf")
            floor = args.piso_s if unit == "s" else args.piso_mb
            n = n_needed(mean, sd, args.margem, floor)
            need[m].append((n, key))
            out.append(f"| {key[0]} | {key[1]} | {key[2]} | {len(xs)} | {mean:.3f} | {med:.3f} | "
                       f"{q3 - q1:.3f} | {sd:.3f} | {cv:.1%} | {n} |")

    # ---- decisão
    n_m1, cell_m1 = max(need["wall_s"])
    n_final = max(args.minimo, n_m1)
    out.append("\n## N recomendado\n")
    for m, (label, _) in METRICS.items():
        n, key = max(need[m])
        out.append(f"- {label}: célula mais exigente {key[0]}/{key[1]}/{key[2]} → N = {n}")
    out.append(f"\n**N da coleta (M1, com mínimo {args.minimo}) = {n_final}**\n")

    # ---- duração estimada: rodadas com e sem medidas de disco/M7
    by_round: dict[int, list[datetime]] = defaultdict(list)
    for r in rows:
        by_round[int(r["round"])].append(datetime.fromisoformat(r["started_at"]))
    rounds = sorted(by_round)
    durs = {}
    for i, rd in enumerate(rounds[:-1]):
        durs[rd] = (min(by_round[rounds[i + 1]]) - min(by_round[rd])).total_seconds()
    disk_rounds = [d for rd, d in durs.items() if rd <= 3]
    plain_rounds = [d for rd, d in durs.items() if rd > 3]
    if disk_rounds and plain_rounds:
        d_disk, d_plain = st.mean(disk_rounds), st.mean(plain_rounds)
        total_h = (3 * d_disk + (n_final - 3) * d_plain) / 3600
        out.append(f"Duração média de uma rodada: {d_disk / 60:.1f} min com disco/M7, "
                   f"{d_plain / 60:.1f} min sem. Coleta com N = {n_final}: ≈ {total_h:.1f} h.\n")

    text = "\n".join(out) + "\n"
    (folder / "resumo.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
