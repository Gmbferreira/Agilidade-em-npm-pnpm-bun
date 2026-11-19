# 2. Design do experimento

> Issue #2 — Sprint 1 · LAB05 · Experimento em software real
> Depende apenas das definições de [01-pergunta-gqm-hipoteses.md](01-pergunta-gqm-hipoteses.md) (M1–M7, H0₁–H0₅).

## 2.1 Decisões de design

| # | Decisão | Escolha | Justificativa | Consequência a declarar |
|---|---|---|---|---|
| A | Scripts de ciclo de vida das dependências | **Configuração padrão** de cada gerenciador (npm executa; pnpm e Bun bloqueiam, salvo lista de permitidos) | O estudo mede o software como ele é usado em operação, que é o que importa para quem usa (seção 5 do enunciado) | O tratamento é "o gerenciador como vem", ou seja, motor de instalação **+** política de scripts. Não se pode afirmar nada sobre o motor isoladamente. Scripts bloqueados são registrados e a M7 verifica se a instalação funciona. |
| B | Origem dos pacotes | **Registry local (Verdaccio)**, pré-populado e **sem uplink durante a coleta** | Elimina a variação da internet, que pode ser maior que o efeito estudado, e não repete centenas de downloads no registry público | Ameaça à validade externa: em CI real os pacotes vêm da internet, então os tempos medidos são um limite inferior. |
| C | Ambiente de execução | **Linux nativo** no notebook do grupo (troca prevista antes da coleta) | A maioria dos runners de CI é Linux, as ferramentas de medição (`/usr/bin/time`, `du`, `hyperfine`) são nativas, e não há camada de virtualização | O piloto só define o N se rodar no Linux (ver 2.8). |

## 2.2 Variáveis

### Variável independente (fator principal)

| Variável | Níveis (tratamentos) | Escala |
|---|---|---|
| **Gerenciador de pacotes** | npm · pnpm · Bun (versões fixadas em #3, configuração padrão) | Nominal |

### Fatores secundários (bloqueio / contexto)

| Fator | Níveis | Por que existe |
|---|---|---|
| **Cenário** | S1 Frio · S2 CI · S3 Quente (2.3) | Os fornecedores costumam medir só o cenário favorável. As hipóteses são testadas **dentro de cada cenário**. |
| **Projeto** | P1 pequeno · P2 médio · P3 grande (2.4) | Evita que o resultado valha só para um tamanho de árvore de dependências. Entra como bloco na análise. |

### Variáveis dependentes

M1 tempo de parede · M2 tempo de CPU · M3a/M3b/M3c disco · M4 nº de arquivos · M5 pico de memória · M6 speedup (derivada) · M7 instalação válida. As definições estão em [01](01-pergunta-gqm-hipoteses.md#13-perguntas-e-métricas).

### Variáveis controladas

| Variável | Como é controlada |
|---|---|
| Máquina e SO | Mesmo notebook, Linux nativo, ligado na tomada, modo de energia fixo, sem outros programas abertos |
| Versões | Node.js, npm, pnpm e Bun fixados e registrados (#3) |
| Registry e rede | Verdaccio em `localhost`, mesmo conteúdo para os três, sem acesso à internet durante a coleta |
| Árvore de dependências | Versões diretas fixadas sem `^`/`~`; lockfiles gerados uma vez contra o registry local e versionados |
| Saída no terminal | `CI=true` e saída de progresso reduzida (barras de progresso também custam tempo) |
| Sistema de arquivos | Mesma partição e mesmo diretório de trabalho para todas as execuções |

### Variáveis de confusão conhecidas (não elimináveis)

- **Runtime:** npm e pnpm rodam sobre o Node.js; o Bun usa o próprio runtime. Isso é inerente ao tratamento e não pode ser separado.
- **Política de scripts:** confundida com o tratamento por decisão (2.1-A).
- **Registry local na mesma máquina:** o Verdaccio consome CPU durante a instalação. O custo é igual para os três tratamentos, mas fica registrado.

## 2.3 Cenários

| Cenário | Cache/store do gerenciador | Lockfile | `node_modules` | Situação real |
|---|---|---|---|---|
| **S1 Frio** | Vazio | Ausente | Ausente | Projeto novo / primeira instalação |
| **S2 CI** | Vazio | Presente (instalação congelada) | Ausente | Pipeline de CI sem cache |
| **S3 Quente** | Cheio (preenchido por instalação não medida) | Presente | Ausente | Reinstalação local / CI com cache |

### Comandos medidos

| Gerenciador | S1 Frio | S2 CI e S3 Quente |
|---|---|---|
| npm | `npm install` | `npm ci` |
| pnpm | `pnpm install` | `pnpm install --frozen-lockfile` |
| Bun | `bun install` | `bun install --frozen-lockfile` |

### Preparação, não medida (executada antes de cada comando medido)

| Ação | S1 | S2 | S3 |
|---|---|---|---|
| Apagar `node_modules` | ✓ | ✓ | ✓ |
| Apagar o lockfile do gerenciador | ✓ | — | — |
| Restaurar o lockfile versionado | — | ✓ | ✓ |
| Limpar cache/store do gerenciador¹ | ✓ | ✓ | ✓² |
| Instalação de aquecimento (preenche o cache) | — | — | ✓ |

¹ npm: `~/.npm/_cacache` · pnpm: diretório de `pnpm store path` · Bun: `bun pm cache rm`. Os comandos exatos e os caminhos ficam em #3 e #4.

² Acrescentado na #4. Sem essa limpeza, o cache do S3 acumulava pacotes das células sorteadas antes, e o conteúdo do cache (e o tempo) dependia da ordem aleatória. Com ela, o aquecimento deixa no cache exatamente o projeto da célula.

## 2.4 Objetos (projetos usados como carga de trabalho)

Os projetos são **carga de trabalho**, não objeto de pesquisa: o que se estuda são os gerenciadores em funcionamento. São gerados a partir de geradores oficiais e congelados no repositório do grupo; nenhum repositório público é minerado ou analisado.

| Projeto | Base | Tamanho esperado da árvore | Verificação funcional (M7) |
|---|---|---|---|
| **P1 pequeno** | API Express + TypeScript | Dezenas de pacotes | `tsc --noEmit` + teste simples |
| **P2 médio** | Template padrão do `create-react-router` (React Router em modo framework, Vite, TypeScript, Tailwind) | Centenas de pacotes | `react-router typegen && tsc` + `react-router build` |
| **P3 grande** | Template do `create-next-app` (TypeScript, ESLint) | Centenas a milhares de pacotes | `next build` |

As versões exatas, o número real de pacotes de cada árvore e o gerador usado ficam registrados em #4 ([04-instrumentacao-piloto.md](04-instrumentacao-piloto.md)).

> **Alteração na #4:** o P2 previsto era o template React + TypeScript do `create-vite`. Com o Vite 8 (rolldown) e o TypeScript 7 (nativo), esse template instala só 28 pacotes, menos que o P1 (78), e deixaria de representar um projeto médio. Ele foi trocado pelo template do `create-react-router` (184 pacotes), que é um gerador oficial, fica entre P1 e P3 e compartilha o React com o P3. Esse compartilhamento é o que o mini-experimento M3c (2.6) precisa. Para a M7, o comando de verificação é sempre executado com o **mesmo runtime** (Node.js), qualquer que seja o gerenciador que instalou. Assim, o que se verifica é a instalação, e não o runtime.

## 2.5 Plano de execução

**Unidade experimental:** uma execução do comando de instalação de uma célula (gerenciador × cenário × projeto).

**Design:** fatorial completo **3 × 3 × 3 = 27 células**, com medidas repetidas e ordem aleatorizada.

| Medida | Repetições por célula | Motivo |
|---|---|---|
| M1, M2, M5 (tempo e memória) | **N** (piloto; estimativa inicial 30) | Variam a cada execução |
| M3a, M3b, M4, M7 (disco, arquivos, validade) | 3 | Praticamente determinísticas; a M7 dobra o tempo da execução |
| M3c (custo do 2º projeto) | 3 por gerenciador | Mini-experimento separado (2.6) |

**Aleatorização:** a coleta é dividida em **rodadas**. Cada rodada executa as 27 células uma vez, em ordem embaralhada com uma semente registrada. Assim, aquecimento da máquina, processos em segundo plano ou deriva ao longo do dia se distribuem entre os tratamentos em vez de favorecer um deles.

**Ciclo de uma execução:** preparação (2.3, não medida) → comando medido com `/usr/bin/time` (M1, M2, M5) → nas rodadas 1–3: `du`/`find` (M3a, M3b, M4), comando de verificação (M7) e registro dos scripts bloqueados (`pnpm ignored-builds`, `bun pm untrusted`).

**Volume estimado:** 27 × 30 = 810 execuções medidas, mais as preparações e as verificações. A ordem de grandeza é de algumas horas de coleta, a confirmar no piloto.

## 2.6 Mini-experimento M3c: custo do segundo projeto

Para cada gerenciador, 3 repetições:

1. Limpar cache/store.
2. Instalar **P2** e medir a pegada real M3b₁.
3. Instalar **P3** (que compartilha dependências com P2, como React) com o mesmo cache/store, e medir M3b₂ sobre `node_modules` de P2 + `node_modules` de P3 + store, numa única chamada de `du`.
4. **M3c = M3b₂ − M3b₁.**

É isso que testa H0₃: espera-se que pnpm e Bun reaproveitem o store e o npm duplique os arquivos.

## 2.7 Relação com as hipóteses

| Hipótese | Métrica | Dados usados | Comparação |
|---|---|---|---|
| H0₁ tempo | M1 (M2 e M6 complementares) | N execuções × 27 células | Entre gerenciadores, dentro de cada cenário, com o projeto como bloco |
| H0₂ disco | M3b | 3 execuções × células de S1 | Entre gerenciadores, por projeto |
| H0₃ 2º projeto | M3c | Mini-experimento 2.6 | Entre gerenciadores |
| H0₄ memória | M5 | N execuções × 27 células | Entre gerenciadores, dentro de cada cenário |
| H0₅ equivalência | M7 | 3 execuções × 27 células | Proporções entre gerenciadores |

Os testes estatísticos, a correção para múltiplas comparações e os tamanhos de efeito são definidos no plano de análise (#7).

## 2.8 Pendências e riscos do design

- **Piloto × troca de SO.** O N só pode ser calculado com dados do ambiente final. Se o piloto (#4) rodar antes da troca para Linux, ele valida apenas o script, e o N é recalculado com uma rodada curta no Linux no início da Sprint 2.
- **Scripts bloqueados.** Se algum projeto falhar na M7 com pnpm ou Bun por causa de um script bloqueado, isso é um **resultado** (registrado), não um erro de execução. O projeto não é trocado.
- **Verdaccio sem uplink.** Antes da coleta, o registry precisa ser populado com todas as versões que os três gerenciadores pedem (inclusive as dependências opcionais de cada plataforma), e o acesso à internet precisa ser desligado. Do contrário, uma requisição externa contamina a medição.
- **Reaproveitamento:** o desenho com tratamentos e repetições segue o que foi praticado no Lab02 (tratamentos LLM × manual), agora com um fator principal e dois fatores de bloqueio.
