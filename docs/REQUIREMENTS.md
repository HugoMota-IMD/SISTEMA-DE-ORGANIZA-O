# Requisitos — V01

Fonte: comando de execução fornecido por Hugo Erazo em 19/10/2026. O COMANDO MESTRE permanece como fonte das decisões de produto; este documento consolida o pedido para execução local. A existência de um requisito nesta lista não constitui evidência de implementação.

## Objetivo e usuários

Aplicativo financeiro pessoal responsivo para uso individual, em casal ou em família, com acessos individuais e dados persistidos no servidor. Deve responder ao saldo disponível, valores a receber, vencimentos, compromisso mensal, dívidas por cartão, término previsto das parcelas, redução futura dos compromissos, projeção de saldo e gastos por classificação.

Uma pessoa pode participar de vários espaços. A participação em um espaço não concede acesso a outro. Na V01 os membros de um espaço compartilham sua visão; informações privadas devem ficar em outro espaço.

| Identificação | Requisito |
| --- | --- |
| SEG-01 | Cadastro, autenticação e encerramento de sessão individual. Persistência e leitura independente do armazenamento do navegador. |
| SEG-02 | Administrador gerencia espaço, participantes e dados; colaborador registra e consulta dados; leitor apenas consulta. A interface e o servidor devem respeitar os perfis, com defesa também no banco. |
| SEG-03 | Todas as operações devem verificar a participação no espaço solicitado. Identificadores de outro espaço não concedem acesso. |
| SEG-04 | Registrar autoria, horário e histórico de operações relevantes. Não guardar senha de cartão, CVV ou número completo; últimos quatro dígitos são opcionais. |
| SEG-05 | Configuração por ambiente, sem credenciais versionadas. Dados fictícios nos testes. Produção exige HTTPS, segredos fortes e configuração de hospedagem aprovada. |

## Modelo financeiro obrigatório

| Identificação | Requisito |
| --- | --- |
| FIN-01 | Contas bancárias, carteiras e espécie: nome, instituição, titular, saldo inicial com data de referência e estado ativo/arquivado. |
| FIN-02 | Receitas: descrição, valor, categoria, pessoa, conta, forma de recebimento, previsão e confirmação efetiva; estados prevista, recebida ou cancelada. |
| FIN-03 | Despesas à vista, parceladas e recorrentes: descrição, estabelecimento/favorecido, categoria/subcategoria, pessoa responsável, valor, compra, competência, vencimento, confirmação, forma, conta/cartão e observações/etiquetas opcionais. |
| FIN-04 | Separar quem registrou, quem pagou e a pessoa a quem o gasto pertence. Na ausência de participante cadastrado, uma identificação textual não concede acesso nem substitui a autoria autenticada. |
| FIN-05 | Pix é forma de pagamento/recebimento/transferência, com atalho ou filtro no mesmo cadastro de movimentações; não deve duplicar lançamentos nem servir como categoria. |
| FIN-06 | Transferência própria movimenta duas contas e não aumenta receitas nem despesas de consumo. |
| FIN-07 | Categorias editáveis iniciais: Alimentação, Moradia, Transporte, Saúde, Educação, Lazer, Compras, Assinaturas, Serviços, Impostos e taxas, Outros. Suportar subcategorias, estabelecimento, canal opcional e filtros independentes. |
| FIN-08 | Saldo realizado deriva do saldo inicial e dos movimentos confirmados em dinheiro. Receitas previstas, limite de cartão e obrigações futuras não constituem dinheiro disponível. |

### Valores, datas e confirmação

Valores monetários são centavos inteiros ou decimal exato, nunca ponto flutuante. O rateio em parcelas deve preservar cada centavo do total. Datas financeiras são datas de calendário, sem conversão por fuso. Para um dia inexistente no mês de destino, a regra da V01 é usar o último dia válido do mês; preservar o dia nominal para as próximas ocorrências.

Vencimento não é confirmação: obrigação vencida continua pendente. Histórico já liquidado não pode mudar silenciosamente; correções exigem cancelamento, estorno ou ajuste explícito rastreável. Repetir a mesma requisição deve retornar o mesmo resultado sem duplicar efeitos. Alterações concorrentes precisam ser detectadas para não sobrescrever operações de outro dispositivo.

### Cartões e obrigações

| Identificação | Requisito |
| --- | --- |
| CAR-01 | Vários cartões: apelido, instituição, titular, quatro dígitos opcionais, limite informado, fechamento, vencimento e conta habitual. |
| CAR-02 | Compra identifica um cartão e gera obrigações vinculadas à compra original. Exibir parcela atual/total, valores, parcelas pagas/restantes, saldo devedor e próximo/último vencimento. |
| CAR-03 | Faturas agregam obrigações; não criam uma segunda dívida. Consolidado não soma compra original + parcelas + fatura. |
| CAR-04 | Pagamento integral ou parcial de fatura gera saída na conta e liquida obrigações, sem gerar outra despesa de consumo. Saldo parcial continua pendente. |
| CAR-05 | Fechamento/vencimento por fatura e correção manual da atribuição de compra, pois processamento bancário pode variar. Compras no fechamento devem seguir uma convenção explícita, ajustável. |
| CAR-06 | Total futuro comprometido e limite estimado devem explicitar a regra. Juros não são presumidos: encargos ou descontos precisam ser informados. |
| CAR-07 | Dívida preexistente aceita parcelas já pagas e preserva seu histórico sem criar saídas de caixa retroativas fictícias. |
| CAR-08 | Quitação, antecipação, estorno e cancelamento preservam valores e histórico. Antecipação com descontos/encargos deve informar como o ajuste altera a obrigação e o caixa. |

As três grandezas são independentes:

- **Saldo devedor:** soma das obrigações constituídas ainda não liquidadas, inclusive atrasadas e parcelas futuras de compras já contratadas. Ocorrências futuras estimadas de uma recorrência não devem aumentar a dívida atual apenas porque a janela de projeção foi ampliada.
- **Compromisso mensal:** obrigações previstas para um mês, com saldo pendente claramente distinguido de valores já pagos.
- **Fluxo de caixa:** entradas e saídas em contas por data de efetivação ou previsão.

Quando uma parcela final de R$ 150 termina em outubro, novembro pode passar de R$ 1.000 para R$ 850 de compromisso, mantendo os demais lançamentos. O saldo devedor somente diminui por liquidação/ajuste confirmado; a passagem de outubro não comprova pagamento.

## Planejamento, relatórios e telas

| Identificação | Requisito |
| --- | --- |
| PLA-01 | “Futuro financeiro” mostra pelo menos 12 meses, extensível: receitas, recorrências, parcelas/faturas, compromisso, saldo projetado, dívidas com fim previsto e redução entre meses. |
| PLA-02 | Projeção parte do saldo realizado e considera previsões conhecidas; atrasos devem permanecer identificáveis, sem sumir porque o mês de vencimento passou. Declarar hipóteses e não prometer ausência de dívida futura. |
| PLA-03 | Simulação de nova compra parcelada mostra impacto mensal sem criar obrigação real ou alterar saldos. |
| PLA-04 | Recorrências podem ter término ou ser indefinidas. Diferenciar mudança da ocorrência atual e alteração das próximas; preservar itens já liquidados. |
| REL-01 | Relatórios por categoria/subcategoria, estabelecimento, pessoa e cartão; receitas/despesas, previsto/realizado e evolução dos compromissos, com período e espaço. |
| REL-02 | Informar sempre a base: compra/competência ou pagamento/caixa. Não somar consumo e pagamento da fatura como despesas na mesma base. |
| REL-03 | Orçamento mensal por categoria e alertas internos: próximos vencimentos, atrasos, faturas, última parcela próxima, orçamento atingido e saldo projetado negativo. |
| UX-01 | Telas/áreas: início, movimentações, a pagar/receber, cartões/faturas, dívidas/parcelamentos, futuro financeiro, cadastros, relatórios/orçamento e configurações/participantes. Agrupar áreas é permitido para reduzir etapas. |
| UX-02 | Layout adaptado ao celular e computador; registro de gasto com poucos passos; mensagens de validação claras. Instalação PWA não implica edição offline. |

## Etapas e entrega

1. Diagnóstico e especificação: inspeção local/Git, requisitos, arquitetura, modelo, premissas, backlog e critérios.
2. Versão funcional: criar espaço → conta/cartão → receita → despesa Pix → compra parcelada → faturas → confirmar pagamento → projeção atualizada, com autenticação, persistência e isolamento.
3. Colaboração e planejamento: participantes, perfis, orçamentos, relatórios, alertas internos, recorrências e simulação.
4. Homologação: testes técnicos e roteiro individual/familiar com evidências e correções.
5. Entrega: versão identificada, manual, limitações, backup/restauração comprovados, manutenção e preparação de publicação. A versão oficial depende de remoto Git privado aprovado e documentação no destino confirmado.

Trabalho local e reversível está autorizado. Publicação, implantação, criação de remoto, envio de código e integrações externas exigem aprovação. Escrita no Drive depende de confirmação de Hugo sobre conta `imd.hugo@dasemper.com` e pasta de destino; a referência ao Drive não comprova acesso ou sincronização.

## Fora da primeira versão

Integração bancária/Open Finance, aplicativos nativos, investimentos, contabilidade empresarial, automações WhatsApp, notificações externas/push e divisão automática/acerto entre pessoas. Edição offline com sincronização e resolução de conflitos exige projeto próprio. Hospedagem não está autorizada; testes locais não comprovam acesso externo nem operação em produção.

## Premissas para execução local

- Moeda inicial BRL, com exibição pt-BR; multimoeda fica para evolução.
- Servidor local e banco persistente são suficientes para homologar; acesso real entre dispositivos depende de servidor acessível e configuração segura aprovada.
- Pessoas responsáveis por lançamentos e usuários autenticados são conceitos separados.
- Credenciais de primeiro acesso são criadas pelo usuário; nenhum usuário/senha padrão deve ser entregue como credencial de produção.
- Qualquer funcionalidade ainda não validada deve constar como pendência no estado atual, ainda que exista no backlog ou na interface.
