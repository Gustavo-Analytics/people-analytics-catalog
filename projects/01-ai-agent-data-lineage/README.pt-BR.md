# 01 · Linhagem de dados de um agente de IA

English: [README.md](README.md)

Mapa interativo (`index.html`, sem dependências) do caminho de um dado de RH, da fonte até a resposta de um agente no chat.

## Problema

Um agente de IA que responde perguntas de People Analytics precisa de dados de pessoas. Os mesmos dados trazem risco: identificação individual, números errados por arquivo incorreto e respostas inventadas quando falta informação.

## Solução em uma frase

O agente **só lê uma camada Gold, anonimizada e agregada**. A camada nominal (Bronze) existe, mas fica fora do alcance dele.

```
Fontes → ETL → Bronze (nominal) → Agregação → Gold (anonimizado) → Pasta de conhecimento → Agente → Chat
```

## Decisões de design

| Decisão | Por quê |
|---|---|
| Medalhão Bronze/Gold | Separa quem calcula (acesso ao nominal) de quem responde (só agregado). |
| Gold sempre em `.xlsx` | A fonte de conhecimento da plataforma não lê `.parquet`. |
| k-anonimato na agregação | Grupo pequeno é identificável por exclusão. Abaixo de k, o valor é suprimido. |
| Arquivo-mestre por visão | Um card por empresa e mês. Evita que o agente junte arquivos de apoio por conta própria. |
| Arquivo "padronizado" por visão | Se existe uma versão com filtro correto (ex.: só vínculos principais), o agente é proibido de usar a versão genérica. |
| Indicador sem fonte = `n/a` | Estimar ou aproximar produz número plausível e errado. Declarar a ausência é mais honesto. |
| Fallback fixo no mestre | Se o mestre ainda não foi indexado, as instruções dizem qual arquivo usar. O agente não escolhe. |

## Lições aprendidas

1. **A indexação demora.** Testar logo após publicar dá falso negativo. Trocar a fonte exige remover, publicar, esperar, readicionar e publicar.
2. **Normalize chaves nos dois lados do join.** Zero à esquerda perdido por leitura numérica faz o cruzamento falhar sem erro.
3. **Todo bloco que depende de um mestre precisa dizer o fallback.** Senão o agente escolhe o arquivo "mais parecido" e erra a escala.
4. **Padronize a escala das colunas percentuais** entre arquivos (fração ou ×100, nunca os dois).
5. **Conversas muito longas no canal de chat podem degradar a resposta.** Reiniciar a conversa resolve.
6. **Não publique o total ao lado de um corte suprimido.** A subtração revela a célula escondida.

## Padrão de instruções do agente

Veja [docs/agent-instructions-pattern.pt-BR.md](docs/agent-instructions-pattern.pt-BR.md).

## Como usar o mapa

Abra `index.pt-BR.html`. Passe o mouse ou clique num bloco para destacar tudo o que o alimenta e tudo o que ele alimenta. Os dados do mapa estão no objeto `DATA` no fim do arquivo e são fictícios. A versão em inglês está em [index.html](index.html).
