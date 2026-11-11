# Backlog priorizado — V01

Atualização: 19/10/2026. Este backlog organiza o comando de Hugo; o estado de execução e as evidências ficam em `CURRENT-STATE.md` e no relatório de entrega. Uma tarefa não está concluída apenas por aparecer aqui.

| Prioridade | Etapa | Item | Critério de saída |
| --- | --- | --- | --- |
| P0 | 1 | Confirmar projeto, raiz Git e arquivos existentes; preservar materiais. | Raiz exclusiva e diagnóstico registrados, sem alterações fora dela. |
| P0 | 1 | Consolidar requisitos, decisões, modelo e limites de escopo. | Requisitos rastreáveis, obrigações únicas, base de cálculo e premissas descritas. |
| P0 | 2 | Estrutura de backend, persistência, configuração e autenticação individual. | Sessões independentes e reinício preservam dados; ausência de segredos no código. |
| P0 | 2 | Espaços e isolamento no servidor e no banco. | Cliente sem vínculo não lê/escreve espaço alheio; leitor não altera; banco bloqueia operação sem contexto autorizado. |
| P0 | 2 | Operações com centavos, datas financeiras, idempotência e concorrência. | R$ 1.000/3 preserva total, datas válidas, repetição sem duplicação e revisão desatualizada recusada. |
| P0 | 2 | Contas e receitas previstas/confirmadas. | Saldo inicial, previsão e realização separados; somente recebimento altera caixa. |
| P0 | 2 | Despesa Pix e transferência própria. | Pix classifica por categoria; transferência não altera totais de receitas/despesas. |
| P0 | 2 | Cartões, parcelamento e faturas. | Obrigações permanecem vinculadas ao cartão correto; totais sem dupla contagem; viradas de calendário válidas. |
| P0 | 2 | Confirmação integral/parcial de obrigações/faturas. | Saída de caixa rastreável, saldo parcial correto e nenhuma nova despesa de consumo. |
| P0 | 2 | Futuro financeiro de 12 meses. | Previsões, compromissos e saldo projetado coerentes; término previsto não quita dívida. |
| P1 | 3 | Participantes e perfis administrador/colaborador/leitor. | Acessos separados, gestão restrita, proteção contra remoção do último administrador. |
| P1 | 3 | Categorias/subcategorias e estabelecimentos editáveis. | Categorias iniciais e agregação Alimentação de R$ 285 comprovadas. |
| P1 | 3 | Recorrências finitas/indefinidas e alteração de ocorrência/futuras. | Não duplica obrigações nem reescreve valores já liquidados. |
| P1 | 3 | Orçamentos e relatórios com base identificada. | Filtros por período/espaço e bases competência/caixa sem mistura silenciosa. |
| P1 | 3 | Alertas internos e simulação de parcelamento. | Alertas calculados a partir dos dados e simulação sem efeitos persistentes. |
| P1 | 3 | Autoria, pagador, responsável e histórico de correções. | Estorno/cancelamento/antecipação rastreáveis e dados históricos preservados. |
| P1 | 3 | Ajuste de fechamento/vencimento/atribuição por fatura. | Compra próxima ao fechamento pode mudar de fatura com justificativa/histórico. |
| P1 | 4 | Homologação técnica e roteiro individual/familiar. | Matriz de aceite executada, evidências reais e falhas conhecidas registradas. |
| P1 | 5 | Backup e restauração em banco isolado de teste. | Restauração recupera usuários, espaços, estado financeiro e histórico; integridade conferida. |
| P1 | 5 | Manual, manutenção, limitações e relatório ao COMANDO MESTRE. | Instalação reproduzível e preparação local revisável. |
| P2 | 5 | Configuração de hospedagem e sincronização Git privada. | Preparativos disponíveis; execução depende de destino e condições aprovados. |
| P2 | posterior | Notificações externas/push, offline completo e integrações. | Novo escopo, suporte técnico e consentimentos confirmados. |

## Bloqueios externos

- Aprovação do repositório Git privado antes de criar remoto/enviar código.
- Aprovação de destino, domínio, TLS, custos e condições de hospedagem antes de publicar.
- Confirmação de conta e destino antes de escrever no Google Drive.
- Validação de Hugo dos fluxos financeiros com dados fictícios antes de considerar a homologação de usuário concluída.

Esses pontos não impedem implementação, testes e documentação locais. Não devem ser descritos como concluídos sem a evidência correspondente.
