# 4. Instrumentação e coleta piloto

> Issue #4 — Sprint 1 · LAB05 · Experimento em software real
> Implementa o plano de execução de [02-design-experimento.md](02-design-experimento.md#25-plano-de-execução) no ambiente de [03-ambiente.md](03-ambiente.md).
> Piloto executado em 19/11/2026, das 19:46 às 20:19 (seed 1243178588).

## 4.1 Projetos de carga

Os projetos ficam em [`projects/`](../projects). As dependências diretas foram fixadas **sem `^` ou `~`**, na versão exata que o npm resolvia em 19/11/2026. Cada projeto guarda um lockfile por gerenciador em `projects/<p>/locks/<gerenciador>/`, gerado uma vez contra o registry local.

| Projeto | Origem | Pacotes no lockfile (npm / pnpm / Bun) | Pacotes instalados¹ | Verificação (M7) |
|---|---|---|---|---|
| **P1** `p1-express-ts` | Escrito à mão: API Express 5.3.0 + TypeScript 7.0.2, com 1 teste `node --test` | 97 / 97 / 97 | **78** | `tsc --noEmit` + `node --test` |
| **P2** `p2-react-router` | `create-react-router@8.5.2`, template padrão (modo framework, Vite 8, Tailwind 4) | 226 / 217 / 226 | **184** | `react-router typegen && tsc` + `react-router build` |
| **P3** `p3-next` | `create-next-app@16.4.6 --yes --ts --eslint --app` (inclui Tailwind 4, padrão do gerador) | 432 / 427 / 436 | **359** | `next build` |

¹ Medido com `npm ls --all --parseable`. O lockfile lista também os binários opcionais de outras plataformas (rolldown, TypeScript 7 nativo, SWC etc.), que não são instalados no Linux x64. O resumo completo está em [`projects/arvores.json`](../projects/arvores.json).

**Troca do P2.** O P2 previsto (template `react-ts` do `create-vite`) instala só 28 pacotes com o Vite 8 e o TypeScript 7, menos que o P1. Ele foi trocado pelo React Router, que é oficial, médio e compartilha o React com o P3 (justificativa completa em [docs/02 §2.4](02-design-experimento.md#24-objetos-projetos-usados-como-carga-de-trabalho)).

**Scripts de ciclo de vida.** Pelo campo `hasInstallScript` do `package-lock.json`, **nenhum pacote das três árvores tem script de instalação no Linux**. O único que tem, o `fsevents` do P2, só é instalado no macOS. Coerente com isso, `blocked_count = 0` em todas as execuções do piloto. A ameaça de docs/01 §1.7 ("o gerenciador fica mais rápido pulando scripts") **não se manifesta nesses projetos**: o ecossistema atual distribui binários nativos como pacotes opcionais por plataforma, e não como `postinstall`. O registro continua no script, para a coleta completa.

## 4.2 Script de benchmark — `scripts/bench.py`

Python 3.15.2 (fixado no `mise.toml`), só biblioteca padrão. Sempre executado com `mise exec --`, para usar as versões fixadas.

| Subcomando | Modo do registry | O que faz |
|---|---|---|
| `lockfiles` | popular | Instala cada projeto com cada gerenciador, guarda o lockfile, reinstala em modo congelado para garantir que o storage tem tudo, roda a M7 e grava `projects/arvores.json`. |
| `run` | coleta | Coleta principal (abaixo). |
| `m3c` | coleta | Mini-experimento do 2º projeto (docs/02 §2.6). |

### Fluxo do `run`

1. **Verificações antes de começar.** O Verdaccio precisa estar no modo coleta, e um pacote fora do storage (`left-pad`) precisa retornar 404, o que prova que não há acesso à internet. O script também avisa se o notebook estiver fora da tomada ou fora do perfil `performance`.
2. **Registro do ambiente.** Grava `env.md` (saída de `scripts/env-info.sh`) e `meta.json` (seed, versões, commit, caminhos de cache).
3. **Rodadas.** Cada rodada embaralha as 27 células com um `random.Random(seed)` e executa cada uma. A ordem inteira pode ser reproduzida a partir da seed.
4. **Preparação, não medida.**
   - O projeto é copiado para `.work/run/<gerenciador>/<projeto>`, uma pasta nova a cada execução, **sem nenhum lockfile**. Isso evita que um gerenciador leia o lockfile de outro (o Bun, por exemplo, migra o `package-lock.json` automaticamente).
   - No S2 e no S3, o lockfile do gerenciador é restaurado.
   - O cache é limpo em **todos** os cenários, com `scripts/clean-cache.sh`.
   - No S3, uma instalação de aquecimento preenche o cache e depois a `node_modules` é apagada.
5. **Medição.** O comando de instalação roda sob `/usr/bin/time -f "%e %U %S %M"`:
   - **M1:** relógio monotônico do Python (`perf_counter_ns`) em volta do processo. O `%e` do GNU time, com resolução de 10 ms, também fica registrado;
   - **M2:** `%U + %S`;
   - **M5:** `%M`, o max RSS.
6. **Medidas de produto, nas rodadas 1–3.**
   - **M3a:** `du -s -B1` da `node_modules`.
   - **M3b:** um único `du` sobre a `node_modules` + os caminhos de cache/store, para que hardlinks sejam contados uma vez.
   - **M4:** `find node_modules -type f | wc -l`.
   - **Scripts bloqueados:** `ignoredBuilds` do `.modules.yaml` no pnpm; `bun pm untrusted` no Bun.
   - **M7:** comando de verificação do projeto, sempre com o Node, via `npm run`.
7. **Gravação.** Cada execução vira uma linha do CSV, gravada assim que termina. Com `--resume`, uma coleta interrompida continua de onde parou.

### Comandos medidos

| Gerenciador | S1 Frio | S2 CI / S3 Quente |
|---|---|---|
| npm | `npm install` | `npm ci` |
| pnpm | `pnpm install` | `pnpm install --frozen-lockfile` |
| Bun | `bun install` | `bun install --frozen-lockfile` |

Todos rodam com `CI=true` e com os três registries apontados para o Verdaccio ([`env/registry.env`](../env/registry.env), carregado pelo próprio script).

### Saída

`data/raw/<data-hora>/` por padrão, ou `--out <pasta>`:

| Arquivo | Conteúdo |
|---|---|
| `runs.csv` | Uma linha por execução (colunas abaixo) |
| `meta.json` | Seed, nº de rodadas, início, commit (`-dirty` se houver alterações não commitadas), versões, máquina, caminhos de cache |
| `env.md` | Registro completo do ambiente no início da coleta |
| `logs/` | Saída de cada instalação e verificação (fora do git) |
| `m3c.csv` | Resultado do subcomando `m3c` |

Colunas do `runs.csv`: `run_id, round, order, started_at, project, pm, scenario, command, exit_code, wall_s` (M1), `wall_s_gnutime, user_s, sys_s, cpu_s` (M2), `maxrss_mb` (M5), `m3a_bytes, m3a_apparent_bytes, m3b_bytes, m4_files, m7_ok, m7_exit, m7_s, blocked_count, blocked_pkgs, pm_version, node_version, machine, kernel, seed`. As colunas de disco, M7 e scripts ficam vazias a partir da 4ª rodada.

### Limitação da M5

O GNU time reporta o `ru_maxrss` dos processos filhos, que é o **maior RSS de um único processo** da árvore, e não a soma. Se um gerenciador dividir o trabalho entre vários processos simultâneos, a M5 subestima o uso total. Isso é registrado como ameaça de construto (#14).

## 4.3 Problemas encontrados e corrigidos antes do piloto

| Problema | Como apareceu | Correção |
|---|---|---|
| Cache do S3 dependia da ordem sorteada | No teste rápido, o store do pnpm no P1/S3 tinha 1,1 GB com pacotes do P3 | O S3 limpa o cache antes do aquecimento (docs/02 §2.3, nota 2) |
| P2 menor que P1 | Contagem de pacotes instalados | P2 trocado (4.1) |
| `pnpm ignored-builds` dava saída inconsistente ("Cannot identify as no node_modules found") | Teste dos lockfiles | Leitura direta do `ignoredBuilds` do `.modules.yaml` |

## 4.4 Resultados do piloto

5 rodadas × 27 células = **135 execuções; 0 falhas de instalação; M7 ok em 81/81 verificações; 0 scripts bloqueados.** Dados em [`data/piloto/`](../data/piloto) e resumo completo por célula (média, mediana, IQR, DP, CV) em [`data/piloto/resumo.md`](../data/piloto/resumo.md).

Os números abaixo são **descritivos e de um piloto com n = 5**. Não respondem às hipóteses, que serão testadas com a coleta completa (#9) e o plano de análise (#7).

### M1 — mediana do tempo de parede (s)

| Projeto | Cenário | npm | pnpm | Bun |
|---|---|---|---|---|
| P1 | S1 Frio | 2,73 | 1,31 | 1,12 |
| P1 | S2 CI | 1,12 | 2,96 | 0,21 |
| P1 | S3 Quente | 0,85 | 0,13 | 0,04 |
| P2 | S1 Frio | 10,52 | 4,86 | 4,45 |
| P2 | S2 CI | 2,62 | 9,19 | 0,75 |
| P2 | S3 Quente | 1,72 | 0,33 | 0,16 |
| P3 | S1 Frio | 25,22 | 11,26 | 10,42 |
| P3 | S2 CI | 8,00 | 25,30 | 3,26 |
| P3 | S3 Quente | 6,84 | 0,75 | 0,48 |

**O pnpm é mais lento com lockfile (S2) do que sem (S1).** O pnpm 12 verifica o lockfile contra o registry por padrão: confere URL do tarball, integridade e histórico de cada pacote, como proteção da cadeia de suprimentos. Para isso, baixa os **manifestos completos** de todos os pacotes (`~/.cache/pnpm/v12/metadata-full`). No P1, o cache de metadados passa de 21 MB no S1 para 43 MB no S2. A opção `--trust-lockfile` desliga essa verificação. Pela decisão 2.1-A (configuração padrão), ela **fica ligada**: é um custo real que o pnpm cobra num pipeline de CI sem cache. A verificação fica registrada por lockfile em `~/.cache/pnpm/lockfile-verified.jsonl`, por isso o S3 não paga esse custo.

### M3 / M4 — disco no S1 (mediana das rodadas 1–3)

| Projeto | Métrica | npm | pnpm | Bun |
|---|---|---|---|---|
| P1 | M3a `node_modules` (MiB) | 37 | 38 | 37 |
| | M3b pegada real (MiB) | 96 | 60 | 41 |
| | M4 arquivos | 1272 | 1276 | 1271 |
| P2 | M3a (MiB) | 122 | 118 | 118 |
| | M3b (MiB) | 424 | 263 | 147 |
| | M4 | 5461 | 5405 | 5367 |
| P3 | M3a (MiB) | 468 | 460 | 466 |
| | M3b (MiB) | 1104 | 790 | 529 |
| | M4 | 21521 | 21497 | 21502 |

Isso confirma o raciocínio de docs/01 §1.3: a M3a é praticamente igual entre os três, e a diferença só aparece na M3b.

### M3c — custo do 2º projeto (P3 depois de P2, cache compartilhado)

| | npm | pnpm | Bun |
|---|---|---|---|
| M3b₁ (só P2) | 147 MiB | 288 MiB | 119 MiB |
| M3b₂ (P2 + P3) | 716 MiB | 1196 MiB | 540 MiB |
| **M3c** | **570 MiB** | **908 MiB** | **421 MiB** |

As 3 repetições deram valores idênticos (diferença < 0,1%). Com a M3c tão determinística, 3 repetições bastam.

**O pnpm teve o maior M3c, o que contraria a expectativa de H1₃.** A decomposição de P2 + P3 com o cache cheio mostra o motivo:

| Componente | npm | pnpm | Bun |
|---|---|---|---|
| `node_modules` dos dois projetos (hardlinks contados uma vez) | 587 MB | 532 MB | 540 MB |
| Arquivos de pacote no cache/store, além dos hardlinks | 129 MB (tarballs comprimidos) | 6 MB | 2 MB |
| Cache de metadados (manifestos) | incluído nos 129 MB | **661 MB** (286 MB abreviados + 375 MB completos) | ≈ 0 |

1. O store de **arquivos** do pnpm é de fato deduplicado: quase tudo é hardlink para a `node_modules`. Quem pesa é o **cache de metadados**, inflado pela verificação do lockfile (manifestos completos).
2. **P2 e P3 compartilham pouco.** A maior parte do P3 é o próprio `next` (≈ 150 MB) e o binário `@next/swc` (≈ 130 MB), que o P2 não usa. Com pouco compartilhamento, a M3c fica perto do tamanho do P3 em qualquer gerenciador.

**Consequência para a análise (#7) e para a coleta (#9).** A M3b e a M3c, como definidas em docs/01, misturam duas coisas: arquivos de pacote, que é o que H1₂ e H1₃ querem testar, e cache de metadados. Proposta: registrar os componentes separadamente na coleta completa e reportar a M3b e a M3c **com e sem** metadados. A separação é direta no pnpm (`metadata*/`) e no Bun (manifestos `*.npm`). No npm, ela exige classificar as entradas do `_cacache` por chave.

## 4.5 N da coleta completa

**Critério.** Para cada célula e métrica, N é o menor n tal que o IC 95% da média tenha meia-largura de no máximo ±5% da média **ou** de um piso absoluto (0,1 s para tempos, 10 MB para memória), o que for maior:

$$t_{0{,}975;\,n-1}\cdot \frac{DP}{\sqrt{n}} \le \max(0{,}05\cdot\bar{x},\ \text{piso})$$

**Por que o piso.** Com só o critério relativo, o N seria **437** (≈ 28 h de coleta). Quem puxa esse número são as células do Bun abaixo de 1 s, que têm picos ocasionais (P2/Bun/S2: 0,62 a 1,95 s). Exigir ±5% de 0,05 s significa ±2,5 ms, uma precisão sem relevância prática. O piso de 0,1 s ainda separa as diferenças mais curtas de interesse, por exemplo Bun × pnpm no S3 (≈ 0,1–0,3 s).

| Critério | N exigido | Duração estimada |
|---|---|---|
| ±5% | 437 | ≈ 28 h |
| ±10% | 112 | ≈ 7,3 h |
| **±5% ou ±0,1 s / ±10 MB (adotado)** | **M1: 116 · M2: 41 · M5: 120** | **≈ 7,5 h** |
| ±5% ou ±0,25 s / ±25 MB | 30 (mínimo) | ≈ 2,1 h |

**N = 120 rodadas**, o padrão de `bench.py run`. Atende à M1 (116) e à M5 (120). As células mais exigentes são P2/Bun/S2 (M1) e P1/pnpm/S2 (M5).

**Duração.** Uma rodada leva 7,5 min com as medidas de disco e M7 (rodadas 1–3) e 3,8 min sem elas. Para 120 rodadas, são ≈ 7,5 h. A coleta pode ser dividida em sessões com `--resume`. Nesse caso, `scripts/env-info.sh` deve ser salvo no início de cada sessão.

**Ressalva.** O DP de cada célula foi estimado com n = 5, o que é impreciso. Se os picos forem mais raros do que o piloto sugere, o N fica folgado; se forem mais frequentes, a análise baseada em mediana e IQR (docs/01 §1.5) é mais robusta que a média.

## 4.6 Pendências para as próximas issues

- **#7 / #9:** separar o cache de metadados na M3b e na M3c (4.4) e decidir como reportar.
- **#9:** rodar `bench.py run` (120 rodadas) e `bench.py m3c --reps 3` com o notebook na tomada, sem outros programas abertos, e salvar o `env.md` de cada sessão.
- **#14:** ameaças registradas aqui: M5 como RSS do maior processo, verificação do lockfile do pnpm, pouco compartilhamento entre P2 e P3 na M3c, e P3 com Tailwind (padrão do gerador).
