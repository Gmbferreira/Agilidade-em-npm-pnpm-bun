# Agilidade em npm, pnpm e Bun

Experimento controlado (LAB05) que compara os gerenciadores de pacotes **npm**, **pnpm** e **Bun** na instalação de dependências de projetos JS/TS: tempo, disco, memória e equivalência funcional.

| Documento | Conteúdo |
|---|---|
| [docs/01-pergunta-gqm-hipoteses.md](docs/01-pergunta-gqm-hipoteses.md) | Pergunta de pesquisa, GQM, métricas e hipóteses |
| [docs/02-design-experimento.md](docs/02-design-experimento.md) | Design do experimento: variáveis, cenários, projetos, plano de execução |
| [docs/03-ambiente.md](docs/03-ambiente.md) | Ambiente controlado: versões fixadas, máquina, cache e registry local |
| [docs/04-instrumentacao-piloto.md](docs/04-instrumentacao-piloto.md) | Projetos de carga, script de benchmark, piloto e N da coleta |

## Reproduzindo o ambiente

O experimento roda em **Linux nativo** (docs/02, decisão 2.1-C). Os passos abaixo foram testados no Arch Linux (Omarchy); em outras distribuições, troque apenas o gerenciador de pacotes do sistema.

### 1. Pré-requisitos do sistema

- `git`, `curl` e `bash`
- [mise](https://mise.jdx.dev/getting-started.html), que instala as versões fixadas de todas as ferramentas
- GNU time, que mede o pico de memória (M5):

```bash
sudo pacman -S time
```

### 2. Clonar e instalar as ferramentas fixadas

```bash
git clone https://github.com/Gmbferreira/Agilidade-em-npm-pnpm-bun.git
```

```bash
cd Agilidade-em-npm-pnpm-bun
```

```bash
mise trust && mise install
```

O `mise install` instala Node.js 26.13.1 (com npm 11.20.0), pnpm 12.21.0, Bun 1.4.5, hyperfine 2.0.0 e Verdaccio 7.1.2. Dentro desta pasta, esses comandos passam a usar exatamente essas versões.

Se o seu shell não tiver o `mise activate` configurado, carregue o ambiente na sessão atual:

```bash
eval "$(mise env -s bash)"
```

### 3. Conferir e registrar o ambiente

```bash
scripts/env-info.sh
```

Confira se as versões batem com a tabela em [docs/03-ambiente.md](docs/03-ambiente.md#31-versões-fixadas). Antes de medir, confira também que o notebook está **na tomada** e com o perfil de energia **`performance`**:

```bash
powerprofilesctl set performance
```

### 4. Subir o registry local

```bash
scripts/registry.sh start popular
```

Aponte os três gerenciadores para ele. O pnpm não lê a mesma variável que o npm, e o arquivo já define as três:

```bash
set -a; source env/registry.env; set +a
```

Instale os projetos uma vez com cada gerenciador para popular o storage (os projetos chegam em #4). Depois, troque para o modo sem internet:

```bash
scripts/registry.sh stop && scripts/registry.sh start coleta
```

### 5. Limpar os caches (cenário frio)

```bash
scripts/clean-cache.sh all
```

Também aceita `npm`, `pnpm` ou `bun` separadamente. O script falha se algum cache não ficar vazio.

### 6. Desligar o registry

```bash
scripts/registry.sh stop
```

## Rodando o benchmark

Detalhes em [docs/04-instrumentacao-piloto.md](docs/04-instrumentacao-piloto.md).

**1. Popular o registry e gerar os lockfiles.** Os lockfiles já estão versionados em `projects/<p>/locks/`. Esta etapa só é necessária para popular um Verdaccio vazio, por exemplo numa máquina nova:

```bash
scripts/registry.sh start popular
```

```bash
mise exec -- python scripts/bench.py lockfiles
```

**2. Trocar o registry para o modo sem internet:**

```bash
scripts/registry.sh stop && scripts/registry.sh start coleta
```

**3. Coletar.** Feche os outros programas e deixe o notebook na tomada, com o perfil `performance`. O padrão é de 120 rodadas (N definido no piloto, cerca de 7,5 h), com saída em `data/raw/<data-hora>/`:

```bash
mise exec -- python scripts/bench.py run
```

Se a coleta for interrompida, continue de onde parou:

```bash
mise exec -- python scripts/bench.py run --out data/raw/<data-hora> --resume
```

**4. Mini-experimento do segundo projeto (M3c):**

```bash
mise exec -- python scripts/bench.py m3c --reps 3 --out data/raw/<data-hora>
```

**5. Resumo e N a partir de uma coleta (usado no piloto):**

```bash
mise exec -- python scripts/n_piloto.py data/piloto
```

## Estrutura

```
mise.toml                 versões fixadas das ferramentas
env/registry.env          variáveis que apontam npm/pnpm/Bun para o Verdaccio
env/verdaccio/            configs do Verdaccio (modos popular e coleta); storage fora do git
scripts/env-info.sh       registra versões, hardware, SO e estado da máquina
scripts/registry.sh       sobe/derruba o Verdaccio
scripts/clean-cache.sh    limpa e confere o cache de cada gerenciador
scripts/bench.py          runner do benchmark (lockfiles, run, m3c)
scripts/n_piloto.py       resumo do piloto e cálculo do N
projects/                 projetos de carga P1–P3 e seus lockfiles (locks/<gerenciador>/)
data/piloto/              dados do piloto (runs.csv, m3c.csv, meta.json, env.md, resumo.md)
data/raw/                 dados da coleta completa
docs/                     documentação do experimento
```
