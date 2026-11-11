# Retorno ao COMANDO MESTRE — Confirmação de pagamentos

Data: **21/10/2026** · Projeto: **CODEX — ORGANIZAÇÃO FINANCEIRA — Organiza** · Versão local: **0.1.2**.

## Entrega

Implementada e verificada a confirmação integral de parcelas pelo saldo pendente, sem redigitar o valor. A lista e os detalhes oferecem **Confirmar pagamento** para obrigação comum e **Pagar fatura** para cartão. O formulário mostra descrição, parcela (por exemplo 3/10), valor pendente, data inicialmente hoje/editável e conta vinculada ativa ou seleção explícita. O botão informa **Confirmar pagamento de R$ X**.

**Alterar valor / pagamento parcial** habilita o valor editável. São recusados zero, negativos, centavos inválidos e pagamentos acima do saldo. O restante continua pendente como **Parcialmente paga**, inclusive quando vencido. A passagem do vencimento nunca confirma pagamento.

A prévia distingue o valor original da parcela do valor original da compra completa. Exibe valor liquidado, saldo da parcela, dívida da compra e do espaço e saldo da conta antes/depois, além das contagens de parcelas. Após sucesso, a resposta atualiza os valores das telas, painel, histórico, faturas e projeção, sem recarregamento manual. A compra original permanece preservada: R$ 1.000,00 com R$ 150,00 pagos apresenta original R$ 1.000,00, liquidado R$ 150,00 e dívida R$ 850,00, sem ajustes.

## Diagnóstico e reaproveitamento

O código anterior já possuía pagamentos parciais, estornos, atualização do estado, revisão, idempotência e transação. O formulário anterior já pré-preenchia o valor, porém mantinha integral e parcial no mesmo campo e selecionava a primeira conta quando não havia vínculo. No detalhe das parcelas havia somente Ajustar; faltava a ação direta de pagamento mostrada na referência de Hugo. Esses pontos foram verificados no código preservado, sem utilizar os dados pessoais da imagem nos ensaios.

A melhoria reaproveita o motor existente. Acrescenta modos explícitos, prévia do pagamento no servidor, seleção de conta válida, revalidação do saldo conferido, indicadores financeiros e caminhos claros de cartão/antecipação. Nenhuma funcionalidade anterior de cadastro foi recriada.

A correção **0.1.1 do cadastro de parcelamentos está implementada**, e suas nove regressões de API e nove grupos de navegador passaram novamente. Os defeitos comprovados de formato `1.000` e âncora do vencimento 31 após fevereiro continuam cobertos. O conflito original relatado por Hugo permanece sem mensagem e passos completos; não foi afirmado que aqueles defeitos eram a causa exata de sua ocorrência.

## Regras financeiras e integridade

- **Fora do cartão:** liquida somente o valor efetivamente confirmado e movimenta a conta escolhida uma vez pelo valor econômico pago. A conta precisa estar ativa. Não há escolha arbitrária da primeira conta.
- **Cartão:** o servidor rejeita pagamento direto da parcela. O caminho usa o saldo da fatura completa, que pode conter outras compras, e mostra sua distribuição na prévia. O consumo original não é criado novamente.
- **Fatura parcial:** alocação por vencimento, data da compra mais antiga, número da parcela e identificador estável como desempate. Uma única conta é usada. Somente obrigações cobertas são liquidadas. Cada alocação gera um registro interno de pagamento/caixa; a soma é exatamente o valor confirmado, sem débito adicional pelo total da fatura. O conjunto é uma operação externa idempotente e uma única transação.
- **Antecipação:** despesas de mês posterior ao mês da data do pagamento exigem escolha explícita e a ação própria `payment.advance`. No cartão, o alvo continua sendo a fatura. Pagar antes do dia do vencimento no mês corrente não exige antecipação. Não se presume desconto, encargo ou juros.
- **Estorno:** confirmação com motivo obrigatório mantém o pagamento original marcado como estornado, acrescenta caixa inverso e reabre o saldo correspondente. Na fatura, o estorno é por pagamento/alocação; para desfazer todo um pagamento distribuído, é necessário estornar suas alocações. Não há estorno agrupado automático nesta versão.
- **Concorrência:** revisão da prévia e saldo esperado são conferidos no servidor, dentro da transação que grava estado, operação idempotente e auditoria. Escritores SQLite são serializados. O botão fica bloqueado durante a requisição. Reenvio após resposta perdida preserva a chave da operação; conflito exige conferir novamente.
- **Erros/permissões:** preenchimento preservado, mensagens junto aos campos, nenhuma quitação otimista. Administrador e colaborador podem confirmar/estornar; leitor somente consulta. Isolamento entre espaços é aplicado no servidor. Todos os valores financeiros usam centavos inteiros.
- **Histórico:** valor original, liquidações anteriores e ajustes existentes são preservados. Liquidação anterior ao aplicativo não gera caixa novo. O saldo e as contagens são derivados das obrigações e pagamentos líquidos; nenhum valor ou pagamento histórico foi reescrito automaticamente.

## Testes executados e resultados

| Verificação | Resultado real |
|---|---|
| `.venv\Scripts\python.exe manage.py test finance --verbosity 1` | **126 aprovados**: 71 testes financeiros anteriores + 20 novos; 17 API/segurança anteriores; 9 API de parcelamento; 9 novos de pagamentos |
| `node tools/test_finance_input.cjs` | **33 verificações monetárias aprovadas** |
| `node --check static/app.js` | Sintaxe aprovada |
| `.venv\Scripts\python.exe tools\verify_payments.py` | **9 grupos aprovados**, computador 1440×1000 e celular emulado 390×844; nenhum erro de console |
| `.venv\Scripts\python.exe tools\verify_payments_concurrency.py` | Duas sessões HTTP simultâneas: **200/409**, um pagamento e um débito; repetição da chave vencedora sem duplicação |
| `.venv\Scripts\python.exe tools\verify_installments.py` | **9 grupos anteriores aprovados** |
| `.venv\Scripts\python.exe tools\verify_ui.py` | Fluxo geral aprovado, incluindo fatura parcial, projeção e simulação; nenhum erro de console |
| `.venv\Scripts\python.exe tools\verify_restore.py` | Backup/restauração completos iguais em outro processo, login administrador/leitor, projeção e recusa de sobrescrita aprovados |
| `manage.py check`, `manage.py makemigrations --check --dry-run`, `python -m pip check` | Sem problemas, nenhuma migração nova e dependências consistentes |

Cobertura comprovada: integral sem digitar valor; parcial e quitação do restante; conta e dívida exatas; original preservado; última parcela; atraso sem pagamento; cartão/fatura sem dívida, consumo ou caixa duplicados; clique duplo; resposta perdida/reenvio; revisão antiga em duas sessões; falha injetada após atualização do estado revertendo documento, revisão, operação e auditoria; falha na segunda alocação sem pagamento parcial persistido; estorno; administrador/colaborador/leitor e outro espaço.

Uma regressão visual específica abriu a parcela **3/10**: original da parcela R$ 100,00, original da compra R$ 1.000,00, liquidado da compra R$ 200,00 → R$ 300,00 e dívida R$ 800,00 → R$ 700,00. Conferir/cancelar não gravou pagamento. O valor parcial acima do saldo mostrou erro junto ao campo, manteve o preenchimento e não gravou. Capturas finais de computador e celular foram inspecionadas visualmente.

Evidências locais, ignoradas pelo Git: `test-results/payments-ui-evidence.json`, `payments-concurrency-evidence.json`, `payments-preservation-result.json`, `payments-local-access.json`, `restore-evidence.json`, `ui-evidence.json`, `installments-ui-evidence.json` e capturas `payments-*.png`. Todos os ensaios financeiros usaram dados fictícios em bases separadas. Nenhum teste gravou ou consultou dados financeiros do banco de uso.

## Raiz e preservação

Chat e raiz Git conferidos; AGENTS.md, README.md, estado e código lidos antes das alterações. Raiz exclusiva efetivamente utilizada:

`C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`

Alterações existentes foram preservadas. Git permanece sem commits e sem remoto. A assinatura SHA-256 de `data/finance.sqlite3` foi idêntica antes/depois, inclusive após reinício e consultas públicas de disponibilidade. Não houve cadastro de teste no banco de uso, limpeza, reinicialização, migração de dados ou correção automática de registros existentes. Não foi realizada nesta melhoria uma nova auditoria dos cadastros pessoais.

Não houve commit, push, envio de código, publicação, escrita no Drive ou alteração de outro projeto. Logs e evidências operacionais permanecem locais e ignorados pelo Git.

## Arquivos alterados nesta tarefa

Existentes modificados, todos relativos à raiz exclusiva acima:

```text
README.md
config/settings.py
finance/domain.py
finance/views.py
finance/test_domain.py
static/app.js
static/app.css
tools/verify_ui.py
docs/CURRENT-STATE.md
docs/MANUAL.md
docs/FINANCIAL-MODEL.md
```

Novos:

```text
finance/test_payments_domain.py
finance/test_payments_api.py
tools/verify_payments.py
tools/verify_payments_concurrency.py
docs/REPORT-V0.1.2-PAYMENTS.md
```

Em `finance/test_domain.py`, quatro chamadas de cenários anteriores foram adequadas às regras explícitas: pagamento de cartão pela fatura e parcelas futuras pela antecipação. As verificações de resultado foram preservadas. Em `tools/verify_ui.py`, o cenário existente passou a escolher a opção parcial e aguardar a prévia antes de confirmar.

## Reinício e migração

**Não exige migração, limpeza ou recadastro.** O servidor local foi reiniciado somente após identificar o processo exato deste projeto na porta 8765. `/api/session` informou **0.1.2**; página e script retornaram **HTTP 200**, com o formulário novo no script servido. Logs anteriores foram preservados.

Hugo deve recarregar a página em **http://127.0.0.1:8765/**. Se o processo local encerrar posteriormente, executar `powershell -File .\start.ps1` na raiz do projeto. Esta tarefa não configurou serviço permanente ou acesso externo.

## Roteiro curto para Hugo homologar

1. Recarregue a página. Em uma dívida fictícia fora do cartão, abra os detalhes e use **Confirmar pagamento**. Confira número, data, conta e valor do botão; confirme sem digitar valor. Confira a parcela, dívida e conta atualizadas.
2. Em outra parcela fictícia de R$ 300,00, use **Alterar valor / pagamento parcial** e confirme R$ 100,00. Verifique Parcialmente paga e saldo R$ 200,00. Abra novamente e confirme integralmente só o restante.
3. Em compra fictícia no cartão, use **Pagar fatura**. Confira o saldo da fatura e a distribuição; um parcial deve deixar as obrigações não cobertas abertas e debitar apenas o valor pago, sem novo consumo.
4. Nos detalhes, use **Estornar** em uma confirmação de teste, informe o motivo e confira a restauração do caixa/dívida e o registro Estornado. Em fatura distribuída, confira o estorno de cada alocação que desejar desfazer.

## Pendências e próxima ação

A implementação e os ensaios locais desta melhoria estão concluídos. **Próxima ação: homologação de Hugo com o roteiro acima.** A validação móvel foi emulada; teste em aparelho físico/acesso externo continua pendente e exige configuração própria de hospedagem/HTTPS. O servidor atual aceita somente localhost.

Estorno agrupado de uma fatura distribuída não foi incluído; o estorno por alocação existente está disponível e documentado. Antecipação não calcula condições contratuais bancárias. Não há reclassificação automática de pagamentos históricos. Se o conflito anterior de cadastro reaparecer, registrar somente mensagem, modalidade e etapa para investigar a ocorrência exata. Publicação, Git remoto e Drive permanecem fora desta tarefa.
