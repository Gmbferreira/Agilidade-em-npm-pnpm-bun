#!/usr/bin/env python3
"""Runner do benchmark npm × pnpm × Bun (issue #4).

Implementa o plano de execução de docs/02 §2.3–2.6. Subcomandos:

  lockfiles   Registry em modo POPULAR. Instala cada projeto com cada gerenciador,
              guarda o lockfile em projects/<p>/locks/<pm>/ e conta os pacotes.
  run         Registry em modo COLETA. Executa R rodadas; cada rodada percorre as
              27 células (gerenciador × cenário × projeto) em ordem embaralhada.
  m3c         Registry em modo COLETA. Mini-experimento do 2º projeto (docs/02 §2.6).

Rode sempre pelo mise, para usar as versões fixadas:
  mise exec -- python scripts/bench.py run --rounds 5 --out data/piloto
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
WORK = ROOT / ".work"          # mesma partição btrfs do store/cache (docs/03 §3.2)
REGISTRY = "http://127.0.0.1:4873"
REGISTRY_MODE_FILE = ROOT / "env" / "verdaccio" / "verdaccio.mode"

PROJECTS = {"P1": "p1-express-ts", "P2": "p2-react-router", "P3": "p3-next"}
PMS = ("npm", "pnpm", "bun")
SCENARIOS = ("S1", "S2", "S3")  # S1 Frio · S2 CI · S3 Quente (docs/02 §2.3)

LOCKFILE = {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml", "bun": "bun.lock"}

# Comandos medidos (docs/02 §2.3)
INSTALL_CMD = {
    ("npm", "S1"): ["npm", "install"],
    ("npm", "S2"): ["npm", "ci"],
    ("npm", "S3"): ["npm", "ci"],
    ("pnpm", "S1"): ["pnpm", "install"],
    ("pnpm", "S2"): ["pnpm", "install", "--frozen-lockfile"],
    ("pnpm", "S3"): ["pnpm", "install", "--frozen-lockfile"],
    ("bun", "S1"): ["bun", "install"],
    ("bun", "S2"): ["bun", "install", "--frozen-lockfile"],
    ("bun", "S3"): ["bun", "install", "--frozen-lockfile"],
}

# Verificação funcional (M7): sempre executada com o Node.js, via npm run,
# qualquer que seja o gerenciador que instalou (docs/02 §2.4).
#   P1: tsc --noEmit + node --test (script "build" do projeto)
#   P2: checagem de tipos + build (o "build" do template React Router não checa tipos)
#   P3: next build (já inclui checagem de tipos)
VERIFY_CMD = {
    "p1-express-ts": "npm run build --silent",
    "p2-react-router": "npm run typecheck --silent && npm run build --silent",
    "p3-next": "npm run build --silent",
}
VERIFY_TIMEOUT_S = 900

# O que NÃO é copiado do projeto para a pasta de trabalho
COPY_IGNORE = shutil.ignore_patterns(
    "locks", "node_modules", ".next", "dist", "build", "*.tsbuildinfo",
    "package-lock.json", "pnpm-lock.yaml", "bun.lock", "bun.lockb", "yarn.lock",
)

CSV_FIELDS = [
    "run_id", "round", "order", "started_at", "project", "pm", "scenario",
    "command", "exit_code", "wall_s", "wall_s_gnutime", "user_s", "sys_s", "cpu_s",
    "maxrss_mb", "m3a_bytes", "m3a_apparent_bytes", "m3b_bytes", "m4_files",
    "m7_ok", "m7_exit", "m7_s", "blocked_count", "blocked_pkgs",
    "pm_version", "node_version", "machine", "kernel", "seed",
]


# ----------------------------------------------------------------------------- utilitários

def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True, **kw)


def load_registry_env() -> None:
    """Aponta os três gerenciadores para o Verdaccio (env/registry.env)."""
    for line in (ROOT / "env" / "registry.env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k] = v
    os.environ["CI"] = "true"


def registry_mode() -> str | None:
    try:
        with urllib.request.urlopen(f"{REGISTRY}/-/ping", timeout=3):
            pass
    except (urllib.error.URLError, OSError):
        return None
    return REGISTRY_MODE_FILE.read_text().strip() if REGISTRY_MODE_FILE.exists() else "?"


def require_registry(mode: str) -> None:
    current = registry_mode()
    if current != mode:
        sys.exit(f"ERRO: o Verdaccio precisa estar no modo '{mode}' (atual: {current or 'parado'}).\n"
                 f"      scripts/registry.sh stop; scripts/registry.sh start {mode}")


def assert_offline() -> None:
    """No modo coleta, um pacote ausente do storage tem de dar 404 (docs/03 §3.4)."""
    probe = "left-pad"
    try:
        urllib.request.urlopen(f"{REGISTRY}/{probe}", timeout=10)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log(f"registry sem internet: '{probe}' → 404 ✓")
            return
        sys.exit(f"ERRO: resposta inesperada do registry para '{probe}': HTTP {e.code}")
    sys.exit(f"ERRO: o registry serviu '{probe}', que não deveria estar no storage. "
             "Há uplink ativo ou o pacote foi baixado na preparação.")


def tool_version(pm: str) -> str:
    return sh([pm, "--version"], cwd=ROOT).stdout.strip().lstrip("v")


def machine_info() -> dict:
    def rd(p: str) -> str:
        try:
            return Path(p).read_text().strip()
        except OSError:
            return "n/d"
    return {
        "machine": f"{rd('/sys/devices/virtual/dmi/id/sys_vendor')} {rd('/sys/devices/virtual/dmi/id/product_name')}",
        "kernel": os.uname().release,
    }


def check_power() -> list[str]:
    """Avisa (sem abortar) se a máquina não estiver na tomada e em performance."""
    warnings = []
    for p in Path("/sys/class/power_supply").glob("*"):
        if (p / "type").exists() and (p / "type").read_text().strip() == "Mains":
            if (p / "online").read_text().strip() != "1":
                warnings.append("notebook NÃO está na tomada")
    try:
        prof = sh(["powerprofilesctl", "get"], check=False).stdout.strip()
        if prof and prof != "performance":
            warnings.append(f"perfil de energia é '{prof}', não 'performance'")
    except FileNotFoundError:
        pass
    return warnings


def cache_paths() -> dict[str, list[Path]]:
    """Diretórios de cache/store de cada gerenciador (mesma lógica de clean-cache.sh)."""
    xdg = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return {
        "npm": [Path(sh(["npm", "config", "get", "cache"], cwd=ROOT).stdout.strip()) / "_cacache"],
        "pnpm": [Path(sh(["pnpm", "store", "path"], cwd=ROOT).stdout.strip()), xdg / "pnpm"],
        "bun": [Path(sh(["bun", "pm", "cache"], cwd=ROOT).stdout.strip())],
    }


def clean_cache(pm: str) -> None:
    r = sh([str(ROOT / "scripts" / "clean-cache.sh"), pm], cwd=ROOT, check=False)
    if r.returncode != 0:
        sys.exit(f"ERRO ao limpar o cache de {pm}:\n{r.stdout}{r.stderr}")


def du_bytes(paths: list[Path], apparent: bool = False) -> int:
    """Um único `du`: arquivos com hardlink são contados uma vez (M3b, docs/01 §1.3)."""
    existing = [str(p) for p in paths if p.exists()]
    if not existing:
        return 0
    cmd = ["du", "-s", "-c", "-B1"] + (["--apparent-size"] if apparent else []) + existing
    out = sh(cmd, check=False).stdout.strip().splitlines()
    return int(out[-1].split()[0]) if out else 0


def count_files(path: Path) -> int:
    """M4: arquivos regulares na node_modules (symlinks não são seguidos)."""
    if not path.exists():
        return 0
    return int(sh(["bash", "-c", f"find '{path}' -type f | wc -l"]).stdout.strip())


def blocked_scripts(pm: str, cwd: Path) -> list[str]:
    """Pacotes com scripts de ciclo de vida bloqueados (docs/01 §1.7)."""
    if pm == "npm":
        return []  # o npm executa todos
    pkgs = set()
    if pm == "pnpm":
        # O pnpm grava os builds ignorados em node_modules/.modules.yaml (chave ignoredBuilds).
        # É a mesma fonte que `pnpm ignored-builds` consulta, sem depender do texto da saída.
        modules = cwd / "node_modules" / ".modules.yaml"
        if modules.exists():
            m = re.search(r"^ignoredBuilds:\n((?:  - .*\n?)*)", modules.read_text(), flags=re.M)
            if m:
                pkgs.update(l.strip()[2:].strip("'\"") for l in m.group(1).splitlines() if l.strip())
        return sorted(pkgs)
    out = sh(["bun", "pm", "untrusted"], cwd=cwd, check=False)
    for line in (out.stdout + out.stderr).splitlines():
        # linhas como "./node_modules/esbuild @0.25.0"
        m = re.match(r"\s*\./node_modules/((?:@[^/\s]+/)?[^\s@]+)", line)
        if m:
            pkgs.add(m.group(1))
    return sorted(pkgs)


def installed_packages(wd: Path) -> int:
    """Pacotes efetivamente instalados (sem os opcionais de outras plataformas), via npm ls."""
    out = sh(["npm", "ls", "--all", "--parseable"], cwd=wd, check=False).stdout.strip().splitlines()
    return len({Path(l).resolve() for l in out[1:]})  # 1ª linha é o próprio projeto


def prepare_workdir(project: str, pm: str, wd: Path, lockfile: bool) -> None:
    if wd.exists():
        shutil.rmtree(wd)
    wd.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECTS_DIR / project, wd, ignore=COPY_IGNORE, symlinks=True)
    if lockfile:
        src = PROJECTS_DIR / project / "locks" / pm / LOCKFILE[pm]
        if not src.exists():
            sys.exit(f"ERRO: lockfile ausente: {src}. Rode o subcomando 'lockfiles' antes.")
        shutil.copy2(src, wd / LOCKFILE[pm])


def timed(cmd: list[str], cwd: Path, logfile: Path) -> dict:
    """Executa o comando medido sob GNU time (M1, M2, M5)."""
    tfile = logfile.with_suffix(".time")
    full = ["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(tfile)] + cmd
    with open(logfile, "w") as fh:
        t0 = time.perf_counter_ns()
        proc = subprocess.run(full, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
        t1 = time.perf_counter_ns()
    parts = tfile.read_text().strip().splitlines()[-1].split()
    tfile.unlink()
    e, u, s, m = float(parts[0]), float(parts[1]), float(parts[2]), int(parts[3])
    return {
        "exit_code": proc.returncode,
        "wall_s": round((t1 - t0) / 1e9, 4),
        "wall_s_gnutime": e,
        "user_s": u, "sys_s": s, "cpu_s": round(u + s, 2),
        "maxrss_mb": round(m / 1024, 1),
    }


def verify(wd: Path, logfile: Path) -> dict:
    t0 = time.perf_counter()
    try:
        with open(logfile, "w") as fh:
            p = subprocess.run(["bash", "-c", VERIFY_CMD[wd.name]], cwd=wd, stdout=fh,
                               stderr=subprocess.STDOUT, timeout=VERIFY_TIMEOUT_S)
        code = p.returncode
    except subprocess.TimeoutExpired:
        code = -1
    return {"m7_ok": int(code == 0), "m7_exit": code, "m7_s": round(time.perf_counter() - t0, 2)}


# ----------------------------------------------------------------------------- contagem de pacotes

def count_packages(pm: str, lock: Path) -> int:
    text = lock.read_text()
    if pm == "npm":
        pk = json.loads(text)["packages"]
        return sum(1 for k in pk if k.startswith("node_modules/") or "/node_modules/" in k)
    if pm == "pnpm":
        sec = text.split("\npackages:\n", 1)[1].split("\nsnapshots:\n", 1)[0]
        return len(re.findall(r"^  ['\"]?[^\s].*:$", sec, flags=re.M))
    # bun.lock (JSONC): conta as chaves de primeiro nível do objeto "packages"
    sec = text.split('"packages": {', 1)[1]
    return len(re.findall(r'^    "[^"]+": \[', sec, flags=re.M))


# ----------------------------------------------------------------------------- subcomando: lockfiles

def cmd_lockfiles(args) -> None:
    require_registry("popular")
    sizes = {}
    for key, project in PROJECTS.items():
        for pm in PMS:
            wd = WORK / "lockfiles" / pm / project
            log(f"{key} {pm}: instalando contra o registry (modo popular)")
            prepare_workdir(project, pm, wd, lockfile=False)
            r = subprocess.run(INSTALL_CMD[(pm, "S1")], cwd=wd, capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit(f"ERRO: {pm} install falhou em {project}:\n{r.stdout[-3000:]}{r.stderr[-3000:]}")
            dest = PROJECTS_DIR / project / "locks" / pm
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wd / LOCKFILE[pm], dest / LOCKFILE[pm])
            n = count_packages(pm, wd / LOCKFILE[pm])
            # Garante que tudo o que o modo frozen pede também está no storage
            shutil.rmtree(wd / "node_modules")
            r2 = subprocess.run(INSTALL_CMD[(pm, "S2")], cwd=wd, capture_output=True, text=True)
            v = verify(wd, wd / "verify.log")
            blocked = blocked_scripts(pm, wd)
            entry = {"lockfile_packages": n, "frozen_ok": r2.returncode == 0,
                     "m7_ok": bool(v["m7_ok"]), "blocked": blocked}
            if pm == "npm":
                lock = json.loads((wd / LOCKFILE[pm]).read_text())["packages"]
                entry["installed_packages"] = installed_packages(wd)
                entry["with_install_script"] = sorted(
                    k.split("node_modules/")[-1] for k, val in lock.items() if val.get("hasInstallScript"))
            sizes.setdefault(key, {})[pm] = entry
            log(f"   {n} pacotes no lockfile · frozen {'ok' if r2.returncode == 0 else 'FALHOU'} · "
                f"M7 {'ok' if v['m7_ok'] else 'FALHOU'} · bloqueados: {', '.join(blocked) or '—'}")
    out = PROJECTS_DIR / "arvores.json"
    out.write_text(json.dumps(sizes, indent=2, ensure_ascii=False) + "\n")
    log(f"resumo salvo em {out.relative_to(ROOT)}")


# ----------------------------------------------------------------------------- subcomando: run

def build_plan(rounds: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    cells = [(p, pm, s) for p in PROJECTS for pm in PMS for s in SCENARIOS]
    plan = []
    for r in range(1, rounds + 1):
        order = cells[:]
        rng.shuffle(order)
        for i, (p, pm, s) in enumerate(order, 1):
            plan.append({"round": r, "order": i, "project": p, "pm": pm, "scenario": s})
    return plan


def cmd_run(args) -> None:
    require_registry("coleta")
    assert_offline()
    for w in check_power():
        log(f"AVISO: {w}")

    out = Path(args.out) if args.out else ROOT / "data" / "raw" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out if out.is_absolute() else ROOT / out
    csv_path, meta_path = out / "runs.csv", out / "meta.json"
    logs = out / "logs"

    done: set[tuple[int, int]] = set()
    if csv_path.exists():
        if not args.resume:
            sys.exit(f"ERRO: {csv_path} já existe. Use --resume para continuar ou outro --out.")
        meta = json.loads(meta_path.read_text())
        seed, rounds = meta["seed"], meta["rounds"]
        with open(csv_path) as fh:
            done = {(int(r["round"]), int(r["order"])) for r in csv.DictReader(fh)}
        log(f"retomando: {len(done)} execuções já registradas (seed {seed})")
    else:
        seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
        rounds = args.rounds
    logs.mkdir(parents=True, exist_ok=True)

    versions = {pm: tool_version(pm) for pm in PMS}
    versions["node"] = tool_version("node")
    mi = machine_info()
    paths = cache_paths()

    if not done:
        (out / "env.md").write_text(sh([str(ROOT / "scripts" / "env-info.sh")], cwd=ROOT).stdout)
        commit = sh(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=False).stdout.strip()
        dirty = bool(sh(["git", "status", "--porcelain"], cwd=ROOT, check=False).stdout.strip())
        meta = {
            "seed": seed, "rounds": rounds, "disk_rounds": args.disk_rounds,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": commit + ("-dirty" if dirty else ""),
            "versions": versions, **mi, "projects": PROJECTS,
            "cache_paths": {k: [str(p) for p in v] for k, v in paths.items()},
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        with open(csv_path, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=CSV_FIELDS).writeheader()

    plan = [p for p in build_plan(rounds, seed) if (p["round"], p["order"]) not in done]
    total = rounds * 27
    log(f"seed {seed} · {rounds} rodadas · {len(plan)} execuções restantes · saída em {out.relative_to(ROOT)}")

    for item in plan:
        project, pm, sc, rnd = PROJECTS[item["project"]], item["pm"], item["scenario"], item["round"]
        run_id = (rnd - 1) * 27 + item["order"]
        wd = WORK / "run" / pm / project
        tag = f"r{rnd:02d}-{item['order']:02d}-{item['project']}-{pm}-{sc}"

        # ---- preparação (não medida), docs/02 §2.3
        prepare_workdir(project, pm, wd, lockfile=(sc != "S1"))
        # Os três cenários partem de cache vazio. No S3, o aquecimento preenche o cache
        # com exatamente este projeto: assim o conteúdo do cache não depende de quais
        # células vieram antes na ordem sorteada.
        clean_cache(pm)
        if sc == "S3":
            warm = subprocess.run(INSTALL_CMD[(pm, sc)], cwd=wd, capture_output=True, text=True)
            if warm.returncode != 0:
                log(f"AVISO: aquecimento falhou em {tag}")
            shutil.rmtree(wd / "node_modules", ignore_errors=True)
            shutil.copy2(PROJECTS_DIR / project / "locks" / pm / LOCKFILE[pm], wd / LOCKFILE[pm])

        # ---- execução medida
        cmd = INSTALL_CMD[(pm, sc)]
        started = datetime.now().isoformat(timespec="seconds")
        m = timed(cmd, wd, logs / f"{tag}.install.log")

        row = {"run_id": run_id, "round": rnd, "order": item["order"], "started_at": started,
               "project": item["project"], "pm": pm, "scenario": sc, "command": " ".join(cmd),
               **m, "pm_version": versions[pm], "node_version": versions["node"],
               "machine": mi["machine"], "kernel": mi["kernel"], "seed": seed}

        # ---- medidas de produto e validade (rodadas 1..disk_rounds), não cronometradas
        if rnd <= args.disk_rounds and m["exit_code"] == 0:
            nm = wd / "node_modules"
            row["m3a_bytes"] = du_bytes([nm])
            row["m3a_apparent_bytes"] = du_bytes([nm], apparent=True)
            row["m3b_bytes"] = du_bytes([nm] + paths[pm])
            row["m4_files"] = count_files(nm)
            blocked = blocked_scripts(pm, wd)
            row["blocked_count"], row["blocked_pkgs"] = len(blocked), ";".join(blocked)
            row.update(verify(wd, logs / f"{tag}.verify.log"))

        with open(csv_path, "a", newline="") as fh:
            csv.DictWriter(fh, fieldnames=CSV_FIELDS).writerow(row)
        status = "ok" if m["exit_code"] == 0 else f"FALHOU ({m['exit_code']})"
        extra = f" · M7 {'ok' if row.get('m7_ok') else 'falhou'}" if "m7_ok" in row else ""
        log(f"[{run_id:>3}/{total}] {item['project']} {pm:<4} {sc}: {m['wall_s']:.2f}s "
            f"{m['maxrss_mb']:.0f}MB {status}{extra}")

    shutil.rmtree(WORK / "run", ignore_errors=True)
    log("coleta concluída.")


# ----------------------------------------------------------------------------- subcomando: m3c

def cmd_m3c(args) -> None:
    """docs/02 §2.6: custo em disco de um 2º projeto (P3) que compartilha dependências com P2."""
    require_registry("coleta")
    assert_offline()
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    paths = cache_paths()
    rows = []
    for rep in range(1, args.reps + 1):
        for pm in random.Random(rep).sample(PMS, len(PMS)):
            clean_cache(pm)
            wd2, wd3 = WORK / "m3c" / pm / PROJECTS["P2"], WORK / "m3c" / pm / PROJECTS["P3"]
            prepare_workdir(PROJECTS["P2"], pm, wd2, lockfile=True)
            prepare_workdir(PROJECTS["P3"], pm, wd3, lockfile=True)
            ok2 = subprocess.run(INSTALL_CMD[(pm, "S2")], cwd=wd2, capture_output=True).returncode == 0
            b1 = du_bytes([wd2 / "node_modules"] + paths[pm])
            ok3 = subprocess.run(INSTALL_CMD[(pm, "S2")], cwd=wd3, capture_output=True).returncode == 0
            b2 = du_bytes([wd2 / "node_modules", wd3 / "node_modules"] + paths[pm])
            rows.append({"rep": rep, "pm": pm, "pm_version": tool_version(pm), "ok": int(ok2 and ok3),
                         "m3b1_bytes": b1, "m3b2_bytes": b2, "m3c_bytes": b2 - b1})
            log(f"rep {rep} {pm:<4}: M3b1 {b1/2**20:.0f} MiB · M3b2 {b2/2**20:.0f} MiB · "
                f"M3c {(b2-b1)/2**20:.0f} MiB")
    with open(out / "m3c.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    shutil.rmtree(WORK / "m3c", ignore_errors=True)
    log(f"salvo em {(out / 'm3c.csv').relative_to(ROOT)}")


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("lockfiles", help="gera os lockfiles e popula o registry (modo popular)")

    r = sub.add_parser("run", help="executa a coleta (modo coleta)")
    r.add_argument("--rounds", type=int, default=120,
                   help="rodadas = repetições por célula (padrão 120, definido no piloto — docs/04 §4.5)")
    r.add_argument("--disk-rounds", type=int, default=3, help="rodadas com disco/M7/scripts (padrão 3)")
    r.add_argument("--seed", type=int, help="semente da ordem aleatória (padrão: sorteada e registrada)")
    r.add_argument("--out", help="pasta de saída (padrão: data/raw/<data-hora>)")
    r.add_argument("--resume", action="store_true", help="continua uma coleta interrompida em --out")

    c = sub.add_parser("m3c", help="mini-experimento do 2º projeto (modo coleta)")
    c.add_argument("--reps", type=int, default=3)
    c.add_argument("--out", required=True)

    args = ap.parse_args()
    for tool in ("node", "npm", "pnpm", "bun"):
        if not shutil.which(tool):
            sys.exit(f"ERRO: '{tool}' não encontrado. Rode via 'mise exec -- python scripts/bench.py ...'.")
    if not Path("/usr/bin/time").exists():
        sys.exit("ERRO: GNU time ausente (sudo pacman -S time).")
    load_registry_env()
    {"lockfiles": cmd_lockfiles, "run": cmd_run, "m3c": cmd_m3c}[args.cmd](args)


if __name__ == "__main__":
    main()
