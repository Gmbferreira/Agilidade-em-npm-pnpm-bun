# 1. Pergunta de pesquisa, GQM e hipóteses

> Issue #1 — Sprint 1 · LAB05 · Experimento em software real
> Objeto de pesquisa: os gerenciadores de pacotes **npm**, **pnpm** e **Bun** em funcionamento (não os seus repositórios).

## 1.1 Pergunta de pesquisa

**QP principal.** Em comparação com o npm, o pnpm e o Bun instalam as dependências de projetos JavaScript/TypeScript mais rápido e com menor uso de disco e memória, produzindo uma instalação funcional equivalente?

Desdobramentos:

- **QP1 (tempo):** a diferença de tempo de instalação existe nos três cenários de uso real: cache frio, cache quente e instalação reprodutível com lockfile?
- **QP2 (disco):** quanto espaço cada gerenciador ocupa num projeto isolado e quanto custa instalar um segundo projeto com dependências em comum?
- **QP3 (memória):** qual o pico de memória de cada gerenciador durante a instalação?
- **QP4 (equivalência):** a instalação resultante funciona da mesma forma (o projeto compila ou testa) com os três gerenciadores?

## 1.2 Objetivo no template de Basili (GQM)

| Elemento | Definição |
|---|---|
| **Analisar** | os gerenciadores de pacotes npm, pnpm e Bun |
| **com o propósito de** | avaliar e comparar |
| **com respeito à** | eficiência da instalação de dependências (tempo, disco e memória), mantendo a equivalência funcional |
| **do ponto de vista de** | desenvolvedores e equipes que mantêm pipelines de CI/CD |
| **no contexto de** | instalação de dependências de projetos JS/TS representativos, em ambiente controlado, com versões mantidas e usadas em produção |

## 1.3 Perguntas e métricas

| Pergunta (GQM) | Métrica | Unidade | Como medir (detalhado em #2 e #4) |
|---|---|---|---|
| Q1. Qual gerenciador instala mais rápido em cada cenário (frio, quente, lockfile)? | **M1** Tempo de parede (wall-clock) da instalação | s | relógio monotônico do runner (`scripts/bench.py`)¹ |
| | **M2** Tempo de CPU (user + sys) | s | `/usr/bin/time`¹ |
| | **M6** Speedup em relação ao npm = M1(npm) / M1(x) | adimensional | derivada de M1 |
| Q2. Quanto disco cada gerenciador ocupa? | **M3a** Tamanho da `node_modules` do projeto | MB | `du` |
| | **M3b** Pegada real = `node_modules` + store/cache do gerenciador, medidos numa única chamada (hardlinks contados uma vez) | MB | `du` |
| | **M3c** Custo incremental de um 2º projeto com dependências em comum | MB | diferença de M3b antes e depois do 2º projeto |
| | **M4** Nº de arquivos na `node_modules` | contagem | `find \| wc -l` |
| Q3. Quanto de memória o processo usa? | **M5** Pico de memória residente (max RSS) | MB | `/usr/bin/time -v` |
| Q4. A instalação é funcionalmente equivalente? | **M7** Instalação válida (o comando de build/teste do projeto passa) | sucesso/falha; proporção | código de saída |

¹ A versão inicial previa o `hyperfine`. Ele foi trocado na #4 porque executa as repetições de um mesmo comando em sequência, o que impede as rodadas embaralhadas do design (docs/02 §2.5), e porque não mede o pico de memória. O runner mede cada execução uma vez, com M1, M2 e M5 juntas. Detalhes em [04-instrumentacao-piloto.md](04-instrumentacao-piloto.md).

**Por que três medidas de disco?** O pnpm e o Bun reaproveitam arquivos de um store global por meio de links (hardlinks) para a `node_modules`. Um `du` só na `node_modules` (M3a) mostra quase o mesmo tamanho para os três e esconde a principal vantagem alegada. Já a pegada real (M3b) e o custo do segundo projeto (M3c) capturam a economia de verdade. Isso é discutido como validade de construto na seção 1.7.

## 1.4 Entidades, atributos e tipo de medida

| Entidade | Classe | Atributo | Interno / externo | Medida |
|---|---|---|---|---|
| Instalação de dependências | Processo | Duração (M1), tempo de CPU (M2) | Interno | Direta |
| Instalação de dependências | Processo | Pico de memória (M5) | Interno | Direta |
| Instalação de dependências | Processo | Sucesso funcional (M7) | Externo | Direta por execução; proporção derivada |
| Árvore instalada (`node_modules` + store) | Produto | Tamanho em disco (M3a, M3b, M3c), nº de arquivos (M4) | Interno | Direta (M3c é derivada) |
| Gerenciador de pacotes (ferramenta) | Recurso | Eficiência / desempenho | Externo | Indireta: inferida de M1–M7; M6 é derivada |

## 1.5 Escalas e estatísticas permitidas

| Variável | Papel | Escala | Estatísticas permitidas |
|---|---|---|---|
| Gerenciador (npm, pnpm, Bun) | Fator / VI | Nominal | Frequência, moda; agrupamento |
| Cenário (frio, quente, lockfile) | Fator / VI | Nominal | Frequência, moda; agrupamento |
| M1, M2, M3a, M3b, M3c, M5 | VD | Razão | Todas: média, média geométrica, mediana, desvio, CV, razões ("2× mais rápido") e testes paramétricos ou não paramétricos |
| M4 | VD | Absoluta (contagem) | Todas as da escala de razão |
| M6 | VD derivada | Razão | Média geométrica dos speedups (mais adequada para razões), mediana |
| M7 | VD | Nominal (binária); a proporção agregada é de razão | Contagem, proporção, teste de proporções |

Como tempo e memória costumam ter distribuição assimétrica (cauda longa por interferência do sistema), a mediana e o IQR vão acompanhar a média na descrição. A escolha dos testes fica no plano de análise (#7).

## 1.6 Hipóteses

As hipóteses são testadas **separadamente para cada cenário** (frio, quente, lockfile). θ representa a medida de posição de cada gerenciador; a estatística exata vem do plano de análise (#7).

**Tempo (M1)**
- H0₁: θ_npm = θ_pnpm = θ_Bun
- H1₁: pelo menos um gerenciador difere dos demais
- Comparações direcionais, com correção para múltiplos testes: H1₁ₐ θ_pnpm < θ_npm; H1₁ᵦ θ_Bun < θ_npm. Bun × pnpm fica bilateral, sem expectativa prévia.

**Disco (M3b e M3c)**
- H0₂: a pegada real em disco é igual entre os gerenciadores
- H1₂: pnpm e Bun ocupam menos disco que o npm
- H0₃: o custo incremental de um 2º projeto é igual entre os gerenciadores
- H1₃: o custo incremental com pnpm e Bun é menor que com npm (efeito esperado grande, pelo reaproveitamento do store)

**Memória (M5)**
- H0₄: o pico de memória é igual entre os gerenciadores
- H1₄: pelo menos um difere. É bilateral porque não há expectativa fundamentada de direção.

**Equivalência (M7)**
- H0₅: a proporção de instalações válidas é igual entre os gerenciadores
- H1₅: as proporções diferem

As expectativas direcionais (pnpm e Bun mais rápidos e mais econômicos) vêm principalmente das **alegações dos próprios projetos**. Por isso elas são tratadas como hipóteses a testar, e não como premissas.

## 1.7 A métrica pode ser "jogada"? (Goodhart, Campbell, McNamara)

- **Lei de Goodhart / Campbell: o gerenciador pode ficar mais rápido fazendo menos trabalho.** Desde a versão 10, o pnpm não executa por padrão os scripts de ciclo de vida das dependências (`postinstall` etc.) [1]. O Bun também não executa scripts arbitrários: só os de uma lista de pacotes confiáveis [2]. O npm executa todos. Comparar só o tempo, portanto, pode premiar quem pula etapas.
  - **Mitigação:** registrar quantos scripts cada gerenciador bloqueou (`pnpm ignored-builds`, `bun pm untrusted`) e medir **M7**. Uma instalação só conta como válida se o projeto compila ou testa depois dela. O design (#2) define se os scripts serão liberados para igualar o trabalho ou se a diferença será tratada como parte do tratamento.
- **Benchmarks dos fornecedores.** Cada projeto publica comparações em cenários favoráveis a si (por exemplo, só cache quente). Medir os três cenários e vários projetos reduz esse viés.
- **Falácia de McNamara: medir só o que é fácil.** Tempo é fácil de medir, mas compatibilidade e segurança também importam para quem escolhe um gerenciador. A M7 e o registro dos scripts bloqueados evitam que a conclusão dependa só de velocidade. Segurança da cadeia de suprimentos fica declarada como fora do escopo da medição.
- **Disco medido do jeito errado.** Conforme a seção 1.3, um `du` ingênuo na `node_modules` esconderia a vantagem do pnpm e do Bun. Por isso existem M3b e M3c.

## Referências

[1] pnpm — CHANGELOG v10.0.0: "Lifecycle scripts of dependencies are not executed during installation by default". https://github.com/pnpm/pnpm/releases/tag/v10.0.0 (acesso em 19/11/2026)
[2] Bun — Lifecycle scripts / trustedDependencies. https://bun.com/docs/pm/lifecycle (acesso em 19/11/2026)
