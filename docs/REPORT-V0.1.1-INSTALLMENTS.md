# Retorno ao COMANDO MESTRE — Correção do cadastro de contas parceladas

Data: 19/10/2026 · Versão local: **0.1.1** · Responsável pelas decisões: Hugo Erazo.

## Raiz, escopo e preservação

Chat e raiz Git confirmados antes de alterações. Raiz efetivamente utilizada:
`C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`.

AGENTS.md, README.md, estado atual e Git foram conferidos. As fontes existentes, ainda sem commits, foram preservadas. Cópias dos arquivos anteriores foram guardadas em test-results para comparar a reprodução. Nenhum banco foi apagado, reinicializado ou migrado; todos os testes usaram bases fictícias isoladas. A base de uso foi consultada somente em leitura, com saída agregada e sem dados pessoais.

Não houve commit, push, publicação, implantação, escrita no Drive ou alteração de outro projeto.

## Causas comprovadas e limite da investigação

Hugo relatou conflito na regra de criação e pediu simplificação. Não informou mensagem exata nem sequência completa. **Não foi demonstrado que os defeitos abaixo correspondem exatamente à ocorrência de Hugo.**

Foram comprovados no navegador, com requisições HTTP e dados fictícios, usando os arquivos anteriores preservados:

1. O formato brasileiro inteiro `1.000` era rejeitado pelo interpretador monetário. A mensagem era “Informe um valor válido, como 1.200,50.” A mesma conta fora do cartão era aceita com `1.000,00`. O campo permanecia preenchido, mas havia somente mensagem geral.
2. No cálculo automático de cartão com vencimento dia 31 e primeira fatura em fevereiro, o primeiro dia reduzido para 28 passava a ser a âncora das parcelas seguintes. Reprodução anterior: **28/02/2027, 28/03/2027, 28/04/2027**. Resultado corrigido: **28/02/2027, 31/03/2027, 30/04/2027**.

O formulário anterior também reunia parcelamento, receita, transferência, recorrência e confirmação imediata. Essa mistura foi removida do cadastro parcelado para simplificar a escolha das regras; não foi declarada como causa comprovada do relato original.

Evidência histórica: test-results/installments-baseline-evidence.json e captura installments-baseline-format.png. O script tools/reproduce_installments.py usa as cópias anteriores locais, não o banco de uso. Logs disponíveis foram consultados por extração sanitizada; não havia traceback que identificasse o conflito específico relatado.

## Correções e melhorias

- Formulário exclusivo em três etapas: conta/modalidade → valores/vencimentos → conferência e confirmação.
- Descrição, estabelecimento/credor, categoria e responsável disponíveis sem misturar forma de pagamento e categoria.
- Modalidade explícita cartão ou fora do cartão. Dívida pendente externa não exige cartão nem escolha antecipada de conta; o pagamento real exige conta válida.
- Modo explícito valor total ou valor da parcela, com validação da correspondência pelo servidor.
- Leitura de valores brasileiros como `1.000`, `1.000,00`, `1000,00` e `333,33`; agrupamentos inválidos são recusados.
- Prévia calculada no servidor pelo mesmo caminho de criação, sem persistência. Mostra total, valores e datas de cada parcela, anteriores pagas, restantes, dívida inicial, último vencimento e vínculo.
- Diferenças de centavos são destacadas antes de confirmar. R$ 1.000/3 mantém 333,34 + 333,33 + 333,33.
- Primeira fatura escolhida por mês, preservando o dia configurado no cartão após meses menores. Vencimentos explícitos legados e faturas ajustadas não são reescritos.
- Mensagens junto aos campos, preenchimento preservado, botões bloqueados durante a requisição e ausência de rastreamentos internos na interface.
- Confirmação vinculada à revisão da prévia. Conflito exige nova conferência; resposta perdida mantém a chave da operação para reenvio sem duplicação.
- Compra e parcelas continuam na mesma transação. Falha de persistência reverte estado, operação e auditoria. Parcelas anteriores não criam caixa e vencimento não confirma pagamento.

## Testes e resultados reais

**97 testes Python aprovados:** 71 financeiros (57 anteriores + 14 novos), 17 de API/segurança anteriores e 9 novos de integração do parcelamento.

**33 verificações da leitura monetária aprovadas**, além de sintaxe JavaScript, dependências e migrações sem divergência.

O novo roteiro de navegador passou em **9 grupos**, usando computador 1440×1000 e celular emulado 390×844:

- Cartão e fora do cartão, incluindo ausência de conta e cartão para dívida externa.
- Total R$ 1.000 em três parcelas e modo valor por parcela.
- Dívida anterior sem saída histórica fictícia; datas nos dias 29, 30 e 31.
- Campos inválidos com mensagem e preenchimento mantido.
- Clique duplo e reenvio do mesmo pedido sem duplicação.
- Resposta perdida depois da gravação, seguida de repetição idêntica sem segunda dívida.
- Alteração real por outra sessão entre prévia e confirmação: conflito, preenchimento preservado e nova conferência obrigatória.
- Administrador/colaborador com gravação, leitor somente consulta/prévia e bloqueio entre espaços.
- Reflexo em faturas, saldo devedor e projeção; nenhuma movimentação de caixa indevida.

A suíte geral anterior de navegador também passou, com fluxo central, duas sessões, projeção de 12/60 meses e simulação sem persistência. As capturas de computador e celular foram inspecionadas visualmente. Não foram usados aparelhos físicos nem dados reais.

O ensaio existente de backup/restauração também foi repetido e passou: snapshot completo, login de administrador/leitor e projeção preservados em outro processo, com recusa de sobrescrita.

Evidências: test-results/installments-ui-evidence.json, ui-evidence.json e capturas installments-outside-desktop.png, installments-card-desktop.png, installments-validation-desktop.png, installments-preview-mobile.png e installments-card-mobile.png. Artefatos locais ignorados pelo Git.

## Registros existentes e banco

A inspeção inicial em leitura encontrou um espaço e nenhum lançamento parcelado na base de uso. Não havia parcelas existentes a revisar como incompletas ou duplicadas. A ferramenta de auditoria não remove ou corrige registros; possíveis coincidências seriam somente candidatas a revisão manual. Evidências agregadas de integridade e preservação ficam em test-results/installments-integrity-before.json e installments-integrity-after.json.

**Não é necessária migração de banco.** É necessário reiniciar o servidor para carregar o código Python e atualizar a página para carregar o formulário. Nenhuma limpeza de dados é necessária ou autorizada. A atualização preserva os dados e as datas já registradas.

O servidor local foi reiniciado nesta execução e respondeu com versão **0.1.1**; o novo formulário foi confirmado no conteúdo servido em localhost. Os logs anteriores foram preservados. Hugo precisa recarregar a página. A comparação antes/depois confirmou documentos financeiros e arquivo SQLite idênticos, conforme test-results/installments-preservation-result.json.

## Arquivos alterados nesta tarefa

Existentes modificados:

```text
README.md
config/settings.py
finance/domain.py
finance/test_domain.py
finance/views.py
static/app.js
static/app.css
tools/verify_ui.py
docs/MANUAL.md
docs/FINANCIAL-MODEL.md
docs/CURRENT-STATE.md
```

Novos:

```text
finance/test_installment_api.py
tools/test_finance_input.cjs
tools/verify_installments.py
tools/reproduce_installments.py
tools/audit_installments.py
docs/REPORT-V0.1.1-INSTALLMENTS.md
```

AGENTS.md e os demais materiais anteriores foram preservados. Bancos fictícios, logs e capturas de teste ficam fora do Git.

## Homologação curta para Hugo

1. Atualizar a página e abrir Parcelamentos e dívidas → Nova conta parcelada.
2. Escolher Fora do cartão, informar uma descrição e continuar. Usar modo Valor total, valor `1.000`, quantidade 3, já pagas 0 e primeiro vencimento 31/01/2027.
3. Conferir R$ 333,34, R$ 333,33 e R$ 333,33, vencendo em 31/01, 28/02 e 31/03. Confirmar e conferir dívida de R$ 1.000, sem saída de caixa.
4. Repetir como dívida anterior com uma parcela já paga: a dívida inicial deve ser R$ 666,66, sem novo débito de caixa.
5. Testar no cartão, escolhendo o mês da primeira fatura; conferir o cartão e todas as datas antes de confirmar. No modo valor da parcela, R$ 100 por três parcelas deve mostrar total R$ 300.

Fazer esses ensaios em espaço de homologação com dados fictícios. Não apagar dados de uso para testar.

## Pendências e próxima ação

Hugo deve homologar o fluxo simplificado no cenário que apresentou conflito. O erro originalmente relatado permanece sem identificação exata; as duas falhas comprovadas acima foram corrigidas e seus cenários foram verificados. Se o conflito persistir, a informação indispensável é o texto da mensagem e se ocorreu antes ou depois de Conferir parcelas/Confirmar cadastro, com a modalidade escolhida. Valores podem ser substituídos por exemplos fictícios.

Continuam válidas as limitações da versão local: sem publicação, sincronização remota aprovada, aparelhos físicos homologados, integração bancária ou edição offline. Git continua sem commits/remoto; nenhuma sincronização externa foi executada.
