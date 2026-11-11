# Critérios de aceite e homologação — V01

Atualização: 19/10/2026. Usar exclusivamente dados fictícios. Esta é a especificação das verificações; resultados efetivamente executados devem ser registrados no estado atual e no relatório. Teste automático local não substitui homologação de Hugo nem comprova publicação.

## Etapa 1 — diagnóstico e decisão

| ID | Verificação | Resultado esperado |
| --- | --- | --- |
| E1-01 | Conferir título, pasta exclusiva, raiz Git, instruções e materiais existentes. | Nenhum comando Git no portfólio e nenhuma modificação em outros projetos. |
| E1-02 | Revisar arquitetura e requisitos antes do código. | Autenticação, isolamento em camadas, persistência, centavos, datas, obrigações e backup com regras explícitas. |
| E1-03 | Conferir limites externos. | Sem remoto, publicação, implantação ou escrita no Drive sem autorização correspondente. |

## Etapas 2–4 — matriz técnica e funcional

| ID | Cenário | Resultado esperado |
| --- | --- | --- |
| F-01 | Criar duas sessões independentes, contas de acesso e espaços. | Cada pessoa autentica com a própria senha; dados persistem no servidor. |
| F-02 | Usuário sem participação tenta listar/ler/alterar espaço alheio, inclusive por URL e identificador conhecido. | Nenhum dado financeiro é retornado ou alterado. |
| F-03 | Leitor tenta registrar receita, despesa, pagamento, alteração de conta e gestão de membro. | Servidor rejeita todas as mutações; leitura autorizada continua disponível. |
| F-04 | Acesso direto ao banco pela conexão da aplicação sem contexto autorizado ou com usuário sem vínculo. | Leitura/escrita protegidas conforme desenho; nenhuma operação pode depender apenas de esconder botão. Controles de arquivo/operador são documentados. |
| F-05 | Saldo inicial de R$ 500; receita prevista de R$ 300; confirmar recebimento. | Antes: realizado R$ 500, projeção inclui R$ 300. Depois: realizado R$ 800 e previsão não é somada novamente. |
| F-06 | Despesa iFood de R$ 100 por Pix e Crepes e Crepes de R$ 185 por outra forma, ambas Alimentação. | Relatório de competência mostra Alimentação R$ 285, independentemente da forma. |
| F-07 | Compra de R$ 1.000 em três parcelas. | Soma exata de 100.000 centavos; cada obrigação vinculada à compra e ao cartão corretos. |
| F-08 | Duas compras em cartões diferentes, uma com virada de ano. | Faturas e obrigações de cada cartão permanecem separadas; datas de ano/mês corretas. |
| F-09 | Compra no fechamento, antes e depois; mês de fevereiro e dia 31. | Regra documentada, datas válidas e possibilidade de correção rastreável por fatura. |
| F-10 | Deixar vencer obrigação sem confirmar pagamento. | Estado segue pendente/atrasado; saldo devedor não diminui e caixa não muda. |
| F-11 | Compromisso outubro R$ 1.000, incluindo última parcela de R$ 150; demais compromissos constantes. | Novembro R$ 850; dívida não é quitada apenas pela passagem do calendário. |
| F-12 | Dívida pendente de R$ 1.000; pagar R$ 150. | Saldo devedor R$ 850; distinguível da redução de compromisso do cenário anterior. |
| F-13 | Pagar fatura integralmente. | Conta tem saída correspondente; obrigação liquidada; relatório de consumo não registra a fatura como segunda despesa. |
| F-14 | Pagar R$ 40 de obrigação/fatura de R$ 100. | Saída de R$ 40 e saldo pendente R$ 60, sem quitação automática. |
| F-15 | Transferir R$ 50 entre contas próprias, inclusive por Pix. | Origem diminui, destino aumenta, total consolidado não muda e receita/despesa de consumo não aumenta. |
| F-16 | Cadastrar dívida de dez parcelas com três já pagas antes da adoção do sistema. | Restam sete obrigações; pagamentos históricos informados não inventam saídas nas contas atuais. |
| F-17 | Reenviar a mesma requisição de lançamento/pagamento com a mesma chave. | Mesmo resultado, uma única obrigação/movimentação e um único efeito de caixa. Chave com conteúdo diferente deve ser recusada. |
| F-18 | Duas sessões alteram o mesmo espaço com a mesma revisão inicial. | Segunda alteração é recusada com conflito e orienta recarregar; não perde a primeira. |
| F-19 | Cancelar lançamento não pago; estornar pagamento confirmado; antecipar com desconto/encargo informado. | Histórico e autoria preservados, valores exatos e efeitos de caixa coerentes; nenhuma alteração silenciosa de item liquidado. |
| F-20 | Criar recorrência, editar só uma ocorrência e depois editar futuras. | Ocorrências distintas, sem duplicação e sem reescrita de pagamentos anteriores. |
| F-21 | Gerar projeção mínima de 12 meses e simular R$ 1.200/6. | Simulação mostra R$ 200/mês e não cria dívida real; premissas e obrigações indefinidas explicitadas. |
| F-22 | Consultar relatórios de competência e caixa com período e espaço. | Base identificada; receitas previstas separadas das recebidas; transferências neutras; cartão sem dupla contagem. |
| F-23 | Configurar orçamento e dados com vencimento próximo, vencido, última parcela e projeção negativa. | Alertas internos correspondem aos dados reais; não alegam serviço push ativo. |
| F-24 | Recarregar, reiniciar servidor e acessar por um segundo cliente com a mesma conta. | Estado, revisões, saldos, projeção e histórico preservados. Teste local identifica seu limite: não comprova uma rede/dispositivo físico externo. |
| F-25 | Enviar formulário sem sessão/CSRF, JSON inválido, centavos fracionários, valor negativo indevido, IDs externos e campos sensíveis de cartão. | Rejeição com erro compreensível; nenhum vazamento de dados, traceback ou armazenamento de campos proibidos. |
| F-26 | Administrador convida/adiciona participante e muda seu perfil; tenta remover o último administrador. | Gestão limitada ao administrador e último administrador preservado. |
| F-27 | Navegar e completar o fluxo principal em largura de celular e computador. | Campos, tabelas, mensagens e ações acessíveis; sem botão essencial escondido. |
| F-28 | Consultar uma recorrência indefinida com projeção de 12 e de 36 meses. | Ampliação da previsão não aumenta a dívida atual nem reduz o limite estimado por incluir novas ocorrências ainda não iniciadas; horizonte e base são explícitos. |

## Etapa 5 — backup e entrega

| ID | Verificação | Resultado esperado |
| --- | --- | --- |
| E5-01 | Fazer backup consistente do banco com usuário, espaço, receitas, despesas, dívida e auditoria. | Arquivo de backup criado em local definido sem expor dados em Git. |
| E5-02 | Restaurar em banco/cópia isolada de teste e validar integridade e totais. | Usuários, vínculos, revisões, saldos, projeções, obrigações e histórico recuperados; produção não é sobrescrita no ensaio. |
| E5-03 | Seguir manual a partir de configuração nova. | Instalação e execução local reproduzíveis; variáveis documentadas, sem segredos padrão de produção. |
| E5-04 | Conferir entrega e relatório. | Versão/etapa, arquivos, decisões, testes reais, falhas, Git/remoto e próxima ação registrados. |

## Roteiro prático individual

1. Criar acesso e espaço “Pessoal teste”.
2. Cadastrar carteira/conta com saldo fictício e um cartão com fechamento/vencimento.
3. Lançar receita prevista e confirmar o recebimento; conferir diferença no saldo.
4. Lançar despesa Pix, outra despesa de Alimentação e transferência própria.
5. Registrar compra parcelada e conferir total original, parcelas, saldo e faturas.
6. Confirmar pagamento parcial e integral, verificando conta, obrigação e relatório.
7. Consultar os 12 meses, atrasos, término previsto e simulação.
8. Reabrir em outra sessão, confirmar persistência e verificar backup restaurado.

## Roteiro prático familiar

1. Criar espaço “Família teste” e acessos individuais para administrador, colaborador e leitor.
2. Garantir que cada pessoa vê somente seus espaços e que o leitor não altera dados.
3. Colaborador registra gasto em nome de outra pessoa; conferir autoria, responsável e pagador separados.
4. Alternar entre “Pessoal teste” e “Família teste”; verificar isolamento e relatórios.
5. Realizar alterações simultâneas e conferir resolução de conflito sem perda de dados.
6. Validar a experiência em celular e computador com Hugo. Registrar aprovação ou ajustes pendentes.

## Cobertura técnica local e aceite ainda pendente

| Grupo | Evidência disponível nesta execução | Limite do aceite |
| --- | --- | --- |
| Autenticação, participantes, isolamento, idempotência, concorrência, CSRF e proteções de gravação | `finance/test_api.py`; 17 testes executados com sucesso em banco temporário e sessões independentes. | Não comprova resistência a um administrador do arquivo SQLite nem homologação externa de segurança. |
| Regras financeiras, datas, cartões, histórico, recorrências, relatórios e projeção | `finance/test_domain.py`; cenários correspondentes a F-05–F-16, F-19–F-23 e F-28, incluindo os exemplos monetários obrigatórios. | Os resultados finais da suíte completa ficam no estado atual; testes usam dados fictícios. |
| Fluxo principal pela interface e adaptação de tela | `test-results/ui-evidence.json` e capturas desktop/móvel; ensaio em navegador com tela móvel emulada. | Não houve teste em aparelho físico. Hugo e família ainda precisam percorrer o roteiro e aprovar o uso. |
| Backup/restauração de dados financeiros completos | `tools/verify_restore.py` e `test-results/restore-evidence.json`: snapshot idêntico em processos separados, incluindo contas, cartão, receitas/despesas, parcelas, pagamentos parciais, caixa, recorrência, orçamento, participantes, auditoria e projeção de 12 meses; sobrescrita recusada. | Ensaio isolado e local. Frequência e cópia externa protegida precisam de destino aprovado. |
| Entrega e operação oficial | Preparativos, documentos e execução em localhost. | Git privado remoto, hospedagem/HTTPS e envio ao Drive dependem das aprovações registradas. Não estão concluídos pela implementação local. |

Uma implementação testada localmente e uma homologação de uso são marcos diferentes. A etapa 4 permanece com aceite humano pendente; a etapa 5 tem preparação local, enquanto publicação, sincronização oficial e documentação externa aguardam autorização. Encerramento dedicado de recorrências existentes não está disponível nesta versão; o modelo financeiro registra essa limitação. O estado atual é a referência para decisões e pendências após esta execução.
