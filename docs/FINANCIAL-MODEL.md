# Modelo financeiro — V0.1

## Representação única

Cada espaço contém contas, cartões, categorias, movimentações originais, obrigações, faturas agregadoras, pagamentos, movimentos de caixa, ajustes, recorrências e orçamentos. IDs internos são UUIDs, resolvidos somente dentro do documento daquele espaço. O documento é salvo em transação, com revisão crescente e chave idempotente única por espaço. A auditoria do servidor registra ator, data, operação e revisão.

A compra original classifica o consumo. Cada parcela gera uma obrigação vinculada a essa compra; despesas à vista e receitas previstas também geram obrigações a pagar/receber. As faturas agrupam as mesmas obrigações do cartão. Portanto, o saldo devedor soma obrigações pendentes uma única vez, sem adicionar o valor original da compra nem o total da fatura novamente.

## Dinheiro e liquidação

Todos os cálculos financeiros usam inteiros em centavos. R$ 1.000 em três parcelas resulta em 33.334 + 33.333 + 33.333 centavos. O formato monetário da interface não altera o valor persistido.

Na correção 0.1.1, o formulário escolhe modo total ou valor da parcela. O servidor recebe o total canônico em centavos e valida que, no modo parcela, ele corresponde exatamente ao valor informado multiplicado pela quantidade inteira. A prévia usa o mesmo caminho de validação e criação sobre uma cópia descartável; não grava dívida, fatura, pagamento ou histórico. Exibe valores/datas exatos e saldo restante depois das parcelas anteriormente pagas. A confirmação fica vinculada à revisão usada na prévia e é rejeitada se outro acesso tiver alterado o espaço.

O cadastro fora do cartão representa uma despesa pendente e pode adiar a escolha da conta. A conta passa a ser obrigatória na confirmação real de pagamento. O formulário exclusivo não mistura parcelamento, recorrência, transferência própria ou pagamento imediato.

Um pagamento confirmado liquida parte ou toda uma obrigação e gera uma entrada/saída na conta informada. Pagamento parcial de fatura é alocado às obrigações pendentes mais antigas, preservando o cartão. Pagamento da fatura não gera uma nova compra nem uma nova categoria de consumo. Estornos geram movimento de caixa inverso e mantêm pagamento original identificado como estornado. Transferências geram saída e entrada em contas próprias, sem receita/despesa nos relatórios.

Parcelas já pagas antes do aplicativo são registradas como liquidação anterior, sem inventar movimentos históricos de caixa. Movimentações confirmadas não podem anteceder a referência do saldo inicial. Não se confirma pagamento ou recebimento com data futura.

Descontos, encargos e reembolsos alteram a obrigação com motivo e valores anteriores/posteriores. Reembolso de valor efetivamente pago exige conta e data; o excesso liquidado é devolvido ao caixa. Uma obrigação liquidada não é alterada silenciosamente. A antecipação é um pagamento confirmado hoje de parcela com vencimento futuro, com ajuste informado quando houver desconto/encargo. Não há estimativa de juros contratuais.

## Confirmação e integridade — 0.1.2

`payment.preview` calcula a confirmação sobre uma cópia descartável, sem persistência nem incremento de revisão. Mostra saldo, alocações, caixa, dívida e contagem de parcelas antes/depois. `mode=full` usa o saldo exato no servidor, dispensando o envio de valor; `mode=partial` exige centavos inteiros positivos até esse saldo. Um valor explícito no modo integral deve coincidir com o saldo completo. Não há crédito por pagamento excedente neste fluxo.

A interface envia a revisão conferida e o saldo esperado. Na transação de gravação o servidor revalida associação, permissão, revisão, conta, data e saldo, antes de persistir documento, chave idempotente e auditoria. A transação SQLite imediata serializa escritores. Clique duplo, repetição da mesma chave e duas sessões sobre a mesma revisão não duplicam a liquidação. Erro durante a gravação desfaz todos os efeitos da operação. Uma nova confirmação independente após atualizar a revisão continua sendo uma nova operação e precisa de saldo disponível.

Pagamento de obrigação comum gera liquidação e caixa vinculados. Obrigação de cartão não pode ser paga diretamente: `invoice.pay` distribui o valor da fatura às obrigações pendentes por vencimento, data da compra mais antiga, número da parcela e UUID como desempate. A prévia usa a mesma ordem. Todas as alocações usam a mesma conta escolhida; não quitam obrigações que não foram cobertas. Cada alocação possui registro interno de pagamento e movimento de caixa, cuja soma é exatamente o valor confirmado; não existe débito adicional pelo total da fatura. Há uma operação idempotente externa e uma transação para o conjunto. O pagamento não cria lançamento de consumo.

O estorno existente continua por registro de pagamento/alocação, com confirmação e motivo obrigatório: mantém o pagamento original marcado como estornado, acrescenta caixa inverso e restaura o saldo correspondente. Para desfazer uma confirmação de fatura distribuída a várias compras, é necessário estornar suas alocações. A interface identifica essas confirmações nos detalhes; não há estorno agrupado automático nesta versão. Datas de estorno não podem anteceder o pagamento nem ultrapassar hoje. Reembolso já devolvido pode impedir estorno integral sem uma operação de correção apropriada.

Antecipação usa `payment.advance`, registrada separadamente. Pagamento comum de despesa com vencimento em mês posterior ao mês da data do pagamento é rejeitado; a prévia exige escolha explícita da antecipação. A antecipação aceita somente despesa com vencimento posterior à data efetiva e nunca uma parcela de cartão avulsa: no cartão o alvo continua sendo a fatura. Pagamentos comuns do mês corrente podem ocorrer antes do dia do vencimento. Nenhum fluxo presume juros, desconto ou encargo.

O valor original da compra permanece em `entry.amount_cents`. O valor original de cada parcela é a divisão canônica desse total em centavos, anterior aos ajustes. O snapshot distingue original, ajustes, valor liquidado líquido e pendente. Sem ajustes, original = liquidado + pendente. Com ajuste, original + ajustes = liquidado + pendente. Liquidações anteriores ao aplicativo contam no liquidado, sem novo caixa; pagamentos estornados deixam de liquidar. `payment_status` distingue parcial, pago e pendente, enquanto `is_overdue` indica atraso independentemente. A compatibilidade do campo anterior `status` foi preservada. As contagens só consideram quitada a obrigação sem saldo; a data de vencimento nunca liquida nada.

## Medidas diferentes

| Medida | Regra |
|---|---|
| Saldo realizado | Saldo inicial referenciado + movimentos de caixa confirmados até a data consultada |
| Saldo devedor atual | Restante das obrigações de despesas contratadas, incluindo parcelas futuras das compras já feitas |
| Compromisso do mês | Obrigações ainda pendentes naquele mês, acrescidas dos atrasos no mês atual |
| Saldo projetado | Saldo realizado + receitas ainda previstas − pagamentos pendentes acumulados |

O fim de uma parcela mensal de R$ 150 pode reduzir o compromisso de R$ 1.000 em outubro para R$ 850 em novembro, mantendo os demais movimentos. Isso é diferente de confirmar R$ 150 de pagamento de uma dívida de R$ 1.000, reduzindo o saldo devedor para R$ 850. A passagem do vencimento nunca confirma quitação.

## Datas, faturas e recorrências

Datas financeiras usam AAAA-MM-DD, sem conversão de fuso horário. Dias 29, 30 e 31 inexistentes usam o último dia do mês; o dia original volta nos meses seguintes. Compra no fechamento entra na fatura que fecha naquele dia. Fechamento/vencimento podem ser ajustados por fatura; parcelas sem pagamento podem mudar entre faturas do mesmo cartão. Regras padrão de cartão já usado não reescrevem histórico.

Na seleção da primeira fatura por mês, o dia do cartão permanece a âncora: vencimento dia 31 com primeira fatura em fevereiro de 2027 produz 28/02, 31/03 e 30/04. A versão anterior podia fixar 28 nos meses seguintes; o erro foi reproduzido e corrigido. Datas explicitamente informadas em registros legados mantêm sua âncora original; faturas já ajustadas continuam prevalecendo. Nenhum registro antigo é recalculado automaticamente por essa correção.

Recorrências são mensais, com valor conhecido e término opcional. IDs determinísticos evitam gerar uma mesma ocorrência duas vezes. Alterações distinguem ocorrência específica e futuras, preservando liquidações. Previsões recorrentes posteriores à data atual têm `forecast=true`: aparecem na projeção, mas não inflam a dívida/recebíveis atuais conforme o horizonte aumenta. A versão atual não oferece uma ação dedicada para encerrar uma recorrência já cadastrada.

## Relatórios e premissas

Categoria responde com o que se gastou; estabelecimento indica onde/para quem; pessoa indica a quem pertence; forma de pagamento indica como se pagou. Pix não é categoria. Categoria principal agrega suas subcategorias. Transferências próprias ficam fora do consumo e das receitas.

Relatórios permitem base de compra ou competência e período mensal; entradas/saídas confirmadas são demonstradas em caixa separadamente. Ajustes reduzem/aumentam o consumo na base da compra; não são uma contabilidade bitemporal de reclassificação por data do ajuste. O histórico completo permite verificar o ocorrido.

A projeção mostra apenas lançamentos conhecidos e recorrências configuradas, carrega atrasos para o mês atual e não presume ausência de novos gastos. Simulação não grava movimentação nem dívida. Recorrências sem término ou valores desconhecidos impedem prometer uma data para ficar sem dívidas. O limite de cartão é estimado pelo limite informado menos parcelas de crédito pendentes, e nunca representa dinheiro disponível.
