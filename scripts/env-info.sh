#!/usr/bin/env bash
# Registra versões, hardware, SO e estado da máquina de medição em Markdown.
#   scripts/env-info.sh                 # imprime na tela
#   scripts/env-info.sh > results/env-AAAA-MM-DD.md   # salva junto com uma coleta
# Deve ser rodado no início de cada sessão de coleta (#4/#5): o estado
# (energia, governor, memória livre) muda de uma sessão para outra.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

rd() { cat "$1" 2>/dev/null || echo "n/d"; }
v()  { mise exec -- "$@" 2>/dev/null | head -1 || echo "n/d"; }

cpu_model="$(lscpu | sed -n 's/^Model name:[[:space:]]*//p')"
cpu_threads="$(nproc)"
cpu_cores="$(lscpu -p=CORE | grep -v '^#' | sort -u | wc -l)"
mem_total="$(free -h | awk '/^Mem:/{print $2}')"
mem_avail="$(free -h | awk '/^Mem:/{print $7}')"
os_name="$(. /etc/os-release && echo "${PRETTY_NAME:-$NAME}")"
fs="$(findmnt -no FSTYPE,OPTIONS -T "$ROOT")"
fs_src="$(findmnt -no SOURCE -T "$ROOT")"
disk_dev="$(lsblk -no PKNAME "$(findmnt -no SOURCE -T "$ROOT" | sed 's/\[.*//')" 2>/dev/null | tail -1)"
[[ -z "$disk_dev" ]] && disk_dev="$(lsblk -dno NAME,TYPE | awk '$2=="disk" && $1!~/^zram/{print $1; exit}')"
disk_model="$(lsblk -dno MODEL "/dev/$disk_dev" 2>/dev/null | xargs)"
disk_size="$(lsblk -dno SIZE "/dev/$disk_dev" 2>/dev/null | xargs)"
luks="não"; lsblk -no FSTYPE | grep -q crypto_LUKS && luks="sim (LUKS)"
ac="n/d"; for p in /sys/class/power_supply/*; do [[ "$(rd "$p/type")" == Mains ]] && ac="$( [[ "$(rd "$p/online")" == 1 ]] && echo 'na tomada' || echo 'na bateria')"; done
profile="$(powerprofilesctl get 2>/dev/null || rd /sys/firmware/acpi/platform_profile)"
swaps="$(swapon --noheadings --show=NAME,TYPE,SIZE | awk '{printf "%s%s (%s, %s)", (NR>1?"; ":""), $1, $2, $3}')"

cat <<EOF
# Registro do ambiente — $(date '+%Y-%m-%d %H:%M:%S %Z')

## Versões

| Ferramenta | Versão |
|---|---|
| Node.js | $(v node --version) |
| npm | $(v npm --version) |
| pnpm | $(v pnpm --version) |
| Bun | $(v bun --version) |
| hyperfine | $(v hyperfine --version | awk '{print $2}') |
| Verdaccio | $(v verdaccio --version) |
| mise | $(mise --version 2>/dev/null | awk '{print $1}') |
| GNU time (\`/usr/bin/time\`) | $( [[ -x /usr/bin/time ]] && /usr/bin/time --version 2>&1 | head -1 || echo "não instalado") |

## Hardware

| Item | Valor |
|---|---|
| Máquina | $(rd /sys/devices/virtual/dmi/id/sys_vendor) $(rd /sys/devices/virtual/dmi/id/product_name) ($(rd /sys/devices/virtual/dmi/id/product_version)) |
| CPU | $cpu_model — $cpu_cores núcleos / $cpu_threads threads |
| Memória | $mem_total total ($mem_avail disponível no momento do registro) |
| Disco | /dev/$disk_dev — $disk_model, $disk_size |

## Sistema operacional

| Item | Valor |
|---|---|
| Distribuição | $os_name |
| Kernel | $(uname -srm) |
| Sistema de arquivos do projeto | $fs_src — $fs |
| Criptografia de disco | $luks |
| Swap | ${swaps:-nenhum} |

## Estado no momento do registro

| Item | Valor |
|---|---|
| Energia | $ac |
| Perfil de energia | $profile |
| Governor da CPU (cpu0) | $(rd /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) |
| EPP (cpu0) | $(rd /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference) |
| Turbo/boost | $(rd /sys/devices/system/cpu/cpufreq/boost) |
| Carga média (1/5/15 min) | $(cut -d' ' -f1-3 /proc/loadavg) |
EOF
