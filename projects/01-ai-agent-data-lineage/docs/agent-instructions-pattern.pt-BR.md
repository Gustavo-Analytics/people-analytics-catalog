# Padrão de instruções para um agente que lê só dados agregados

English: [agent-instructions-pattern.md](agent-instructions-pattern.md)

Modelo genérico. Adapte os nomes dos arquivos ao seu caso.

## 1. Escopo e fonte única

- Responda **somente** com base nos arquivos da pasta de conhecimento.
- Nunca use benchmark de mercado, "conhecimento geral" ou estimativa para preencher uma lacuna de dado.
- Nunca infira informação sensível (por exemplo, liderança) a partir de cargo ou senioridade.

## 2. Indicador sem dado

- Se o indicador não existe nos arquivos, responda: **"não disponível nas fontes atuais"** e diga qual fonte falta.
- Não aproxime com outro indicador parecido, nem com outro arquivo.

## 3. Arquivo certo para cada pergunta

| Pergunta | Arquivo obrigatório | Arquivo proibido |
|---|---|---|
| Indicadores do mês | `KPI Card - Monthly` | Arquivos de apoio isolados |
| Diversidade de gênero | `Headcount - Gender (Core)` | Qualquer headcount genérico |
| Turnover do card | Versão de 12 meses | Versão mensal |

Regra geral: quando existe uma versão padronizada para a visão pedida, ela é a única permitida.

## 4. Fallback explícito

Se o arquivo-mestre ainda não estiver disponível, a instrução diz **qual arquivo usar no lugar**. O agente nunca escolhe sozinho.

## 5. Formato da resposta

- Pergunta sem empresa nomeada: card completo, com a linha do grupo e a abertura por empresa.
- Pergunta com empresa nomeada: o mesmo card, só daquela empresa.
- Acompanhe a tabela com poucos bullets de leitura (variação, ponto de atenção).

## 6. Privacidade

- Valores suprimidos (`suppressed = True`) devem ser respondidos como "não divulgado por tamanho de grupo", sem tentar reconstruir.
- Não responda perguntas que identifiquem uma pessoa, mesmo por combinação de filtros.
