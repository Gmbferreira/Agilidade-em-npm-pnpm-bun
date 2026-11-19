# 3. Ambiente controlado e versões fixadas

> Issue #3 — Sprint 1 · LAB05 · Experimento em software real
> Implementa as variáveis controladas de [02-design-experimento.md](02-design-experimento.md#22-variáveis) (máquina, versões, registry, limpeza de cache).
> Refeita no Linux nativo em 19/11/2026, conforme a decisão 2.1-C. A versão anterior, feita no Windows, foi descartada.

Os passos para reproduzir o ambiente estão no [README](../README.md). Este documento registra **o que** foi fixado e **por quê**.

## 3.1 Versões fixadas

Todas as ferramentas são instaladas pelo [mise](https://mise.jdx.dev) a partir do [`mise.toml`](../mise.toml) na raiz do repositório. Dentro da pasta do projeto, `node`, `npm`, `pnpm`, `bun` etc. resolvem sempre para estas versões, independentemente do que estiver instalado no sistema.

| Ferramenta | Versão | Critério da escolha (consultado em 19/11/2026) |
|---|---|---|
| Node.js | **26.13.1** | Linha LTS **ativa** (Lithium; LTS desde 28/10/2026, manutenção a partir de 20/10/2027) [1]. É a linha recomendada para produção. |
| npm | **11.20.0** | Versão **embutida** no Node.js 26.13.1. É o npm que um usuário (e a maioria das imagens de CI) recebe ao instalar o Node. O npm 12.2.3 já existe, mas não é o distribuído com a LTS. |
| pnpm | **12.21.0** | dist-tag `latest` do pnpm no registry [2]. |
| Bun | **1.4.5** | Última versão estável [3]. |
| hyperfine | **2.0.0** | Ferramenta de medição de M1 e M2 (docs/01 §1.3). |
| Verdaccio | **7.1.2** | dist-tag `latest` [4]. Registry local (decisão 2.1-B). |
| Python | **3.15.2** | Runner do benchmark e cálculo do N (#4); só biblioteca padrão. Acrescentado ao `mise.toml` na #4. |
| GNU time | **1.10** | Pacote `time` do Arch (`sudo pacman -S time`), fora do mise. Mede a M5 (`/usr/bin/time -v`, max RSS). |

`npm` e `pnpm` rodam sobre o Node.js 26.13.1; o Bun usa o próprio runtime (confusão inerente ao tratamento, docs/02 §2.2).

O `mise.toml` também define `CI=true` para todos os comandos, o que reduz a saída de progresso (variável controlada "Saída no terminal").

## 3.2 Máquina de medição

Gerado por [`scripts/env-info.sh`](../scripts/env-info.sh) em 19/11/2026. O script deve ser rodado **no início de cada sessão de coleta**, e a saída deve ser salva junto com os resultados, porque o estado da máquina (energia, governor, memória livre) muda de uma sessão para outra.

| Item | Valor |
|---|---|
| Máquina | Lenovo IdeaPad 3 15ALC6 (82MF) |
| CPU | AMD Ryzen 5 5500U — 6 núcleos / 12 threads |
| Memória | 5,6 GiB |
| Disco | NVMe SSSTC CL1-4D256, 238,5 GB |
| Distribuição | Omarchy (baseada em Arch Linux) |
| Kernel | Linux 7.1.9-arch1-2 x86_64 |
| Sistema de arquivos | btrfs (`compress=zstd:3`) sobre LUKS (disco criptografado) |
| Swap | zram 5,6 GiB (prioridade 100) + swapfile 5,6 GiB |
| Energia na coleta | na tomada; perfil `performance`; governor e EPP `performance`; boost ligado |

### Observações que afetam a medição

- **Memória pequena (5,6 GiB) com zram.** Se a instalação de P3 encostar no limite, o kernel comprime páginas no zram, e isso custa CPU e tempo. O pico de memória (M5) e a memória disponível antes de cada sessão devem ser registrados. Feche navegador e editor durante a coleta.
- **LUKS + compressão zstd do btrfs.** Toda escrita em disco passa por criptografia e compressão. O custo é o mesmo para os três gerenciadores, mas os tempos absolutos não são comparáveis com máquinas sem essas camadas (validade externa). A compressão **não** afeta o `du`, que mede o tamanho lógico dos arquivos.
- **Perfil de energia.** Deve estar em `performance` e na tomada antes de cada sessão (`powerprofilesctl get`). O `env-info.sh` registra isso.

### Como os gerenciadores gravam no btrfs (impacto na M3b)

O pnpm e o Bun podem, em tese, usar cópias *reflink* em sistemas de arquivos que as suportam, como o btrfs. O `du` contaria essas cópias como espaço cheio, o que inflaria a M3b. Por isso o comportamento foi **verificado** nesta máquina, com a configuração padrão de cada um:

| Gerenciador | Como a `node_modules` recebe os arquivos | Evidência |
|---|---|---|
| npm | Cópia independente (extraída do cache) | `stat`: 1 link por arquivo |
| pnpm | **Hardlink** para o store (`~/.local/share/pnpm/store/v11`) | `stat`: 2 links; `find -samefile` acha o arquivo no store |
| Bun | **Hardlink** para o cache (`~/.cache/.bun/install/cache`); backend padrão `hardlink` | `stat`: 2 links; `find -samefile` acha o arquivo no cache |

Como são hardlinks, um único `du` sobre `node_modules` + store conta cada arquivo uma vez, que é exatamente a M3b definida em docs/01. **Condição:** o projeto e o store/cache precisam estar na **mesma partição**. Entre partições diferentes, o hardlink é impossível e os gerenciadores passam a copiar. Isso foi observado num teste em `/tmp` (tmpfs), onde o Bun passou a copiar. Os projetos de #4 ficam dentro do repositório, no mesmo btrfs do `$HOME`.

## 3.3 Limpeza de cache (cenários S1 Frio e S2 CI)

Feita por [`scripts/clean-cache.sh`](../scripts/clean-cache.sh) `npm|pnpm|bun|all`. O script apaga o cache e **confere** que não sobrou nenhum arquivo; se sobrar, falha.

| Gerenciador | O que é apagado | Comando usado | Observação |
|---|---|---|---|
| npm | `~/.npm/_cacache` (`npm config get cache` + `/_cacache`) | `npm cache clean --force` | Apaga o cache de conteúdo inteiro. |
| pnpm | Store `~/.local/share/pnpm/store/v11` (`pnpm store path`) **e** cache de metadados `~/.cache/pnpm` | `rm -rf` dos dois | `pnpm store prune` **não serve**: só remove pacotes que nenhum projeto referencia. Sem apagar o cache de metadados, o pnpm não precisa baixar os manifestos de novo e o cenário não seria frio. |
| Bun | `~/.cache/.bun/install/cache` (`bun pm cache`) | `bun pm cache rm` | Remove pacotes e manifestos em cache. |

Os caminhos do pnpm e do Bun dependem de `XDG_CACHE_HOME`. Sem essa variável, por exemplo num shell limpo, o Bun usa `~/.bun/install/cache`. Por isso o script não fixa os caminhos: pergunta a cada gerenciador (`npm config get cache`, `pnpm store path`, `bun pm cache`) e usa a resposta.

O script **não** apaga `node_modules` nem lockfiles. Isso faz parte da preparação de cada projeto e fica no script de medição (#4).

## 3.4 Registry local (Verdaccio)

Implementa a decisão 2.1-B: todos os pacotes vêm de `http://127.0.0.1:4873`, e durante a coleta o registry **não tem acesso à internet**.

O registry tem dois modos, que compartilham o mesmo storage (`env/verdaccio/storage/`, fora do git):

| Modo | Config | Uplink | Quando usar |
|---|---|---|---|
| **popular** | [`config.popular.yaml`](../env/verdaccio/config.popular.yaml) | `registry.npmjs.org` | Só na preparação: instalar cada projeto com os três gerenciadores para que tudo o que eles pedem fique salvo no storage. **Nunca medir neste modo.** |
| **coleta** | [`config.coleta.yaml`](../env/verdaccio/config.coleta.yaml) | nenhum | Durante a medição. Um pacote ausente do storage retorna 404 em vez de ir à internet. |

Controle: `scripts/registry.sh start popular|coleta`, `stop` e `status`. O Verdaccio roda pelo mise (pacote npm fixado), sem Docker e sem precisar de root.

### Apontando os gerenciadores para o registry

Cada gerenciador lê uma variável de ambiente **diferente**. As três estão em [`env/registry.env`](../env/registry.env):

| Gerenciador | Variável |
|---|---|
| npm | `NPM_CONFIG_REGISTRY` |
| pnpm | `PNPM_CONFIG_REGISTRY` |
| Bun | `BUN_CONFIG_REGISTRY` |

> **Armadilha encontrada na verificação:** o pnpm 12 **ignora** `NPM_CONFIG_REGISTRY`. Com só essa variável, o pnpm instalou direto do registry público, mesmo com o Verdaccio no modo coleta. Ou seja, sem que se percebesse, ele estaria medindo a internet. Por isso a verificação abaixo testa os três gerenciadores separadamente.

### Verificação (19/11/2026)

Com um projeto de teste (`is-number@7.0.0`, `chalk@5.3.0`):

| Teste | npm | pnpm | Bun |
|---|---|---|---|
| Modo popular: instalar (lockfile aponta para `127.0.0.1:4873`) | ✓ | ✓ | ✓ |
| Modo coleta, cache limpo, pacotes no storage: instalar | ✓ | ✓ | ✓ |
| Modo coleta, pacote **fora** do storage (`left-pad`): instalação **deve falhar** | ✓ falhou | ✓ falhou | ✓ falhou |
| `clean-cache.sh all` deixa os caches vazios | ✓ | ✓ | ✓ |

Antes de cada coleta, o script de #4 deve repetir a última linha (um pacote fora do storage precisa falhar) para garantir que nenhuma requisição vá à internet.

## 3.5 Pendências para #4

- Popular o Verdaccio com os projetos P1–P3, incluindo as dependências opcionais de plataforma que cada gerenciador pede.
- Registrar o número real de pacotes de cada árvore.

## Referências

[1] Node.js Release Schedule. https://github.com/nodejs/Release/blob/main/schedule.json e https://nodejs.org/dist/index.json (acesso em 19/11/2026)
[2] pnpm — dist-tags no registry npm (`npm view pnpm dist-tags`). (acesso em 19/11/2026)
[3] Bun — `npm view bun dist-tags.latest`. (acesso em 19/11/2026)
[4] Verdaccio — `npm view verdaccio dist-tags`. (acesso em 19/11/2026)
