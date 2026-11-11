# Manual de uso e operação — Organiza V0.1

## Acesso no piloto hospedado preparado

Quando o piloto for liberado, cada participante deverá usar sua própria conta. Quem já tem cadastro usará seu usuário e senha no novo endereço. Uma solicitação nova fica pendente até que alguém com administração técnica a ative. A administração técnica gerencia o acesso em **Contas de usuário**. O administrador de um espaço concede a participação e o papel dentro desse espaço. Consulte **Configurações → Participantes** para conferir identificação, papel e situação.

Durante a migração, o modo de consulta bloqueia formulários, inclusive login. A liberação será informada após a reconciliação. O endereço público, o teste em aparelhos físicos e a retomada real após inatividade dependem da publicação aprovada. [Estado da preparação e homologação](REPORT-V0.2-NEON-RENDER.md)

## Abrir nesta máquina

Na raiz exclusiva do projeto, execute `powershell -File .\start.ps1`. O iniciador confere a raiz Git, a instalação e o banco existentes e inicia o servidor em segundo plano em `http://127.0.0.1:8765`. Se já estiver ativo, não cria outro processo. Abra esse endereço no navegador. Consulte com `powershell -File .\status.ps1` e encerre apenas o Organiza com `powershell -File .\stop.ps1`. Fechar o terminal não encerra o servidor em segundo plano. O iniciador não cria banco vazio, não reinstala o ambiente e não migra dados automaticamente; se faltar instalação ou banco, interrompe com instrução.

Para o acesso privado Tailscale, consulte [PRIVATE-ACCESS.md](PRIVATE-ACCESS.md): máquina e banco oficiais, configuração escopada do Serve, clientes Windows/iPhone e opção de início no logon. **HTTPS ativo e testado: https://desktop-flde4sk.tail08d4d6.ts.net/**. O comando de status distingue Tailscale conectado de rota Serve efetivamente configurada. Nos clientes, conectar o Tailscale antes de abrir o endereço e usar o acesso individual do Organiza. Não é necessário habilitar Funnel. Falta homologar os três dispositivos físicos por outra rede.

O banco de uso fica em `data/finance.sqlite3`. Não há conta, senha ou dados financeiros de exemplo predefinidos. Crie seu acesso e seu primeiro espaço. A chave local de sessões é gerada em `data/.local-secret`, ignorada pelo Git; preserve esse arquivo durante a operação. A configuração opcional usa `.env`, conforme `.env.example` sem credenciais reais.

## Primeiro fluxo

1. Crie um acesso pessoal e um espaço, por exemplo Pessoal ou Família.
2. Cadastre uma conta ou carteira, com saldo inicial e data de referência. Registre somente movimentações posteriores a essa referência para não duplicar o saldo que já foi informado.
3. Cadastre o cartão com apelido, titular, limite, fechamento e vencimento. Os quatro últimos dígitos são opcionais. Não informe número completo, CVV ou senha.
4. Registre a receita. Uma receita prevista fica a receber; confirme o recebimento para alterar o dinheiro disponível.
5. Para despesa Pix, escolha categoria e estabelecimento separadamente, informe a conta e indique se o pagamento já ocorreu. O atalho Pix usa o mesmo registro financeiro.
6. Em Parcelamentos e dívidas, abra Nova conta parcelada. Escolha cartão ou fora do cartão, informe os valores e confira o cronograma antes de confirmar. O cadastro comum de movimentações fica reservado a um lançamento ou recorrência; o parcelamento possui formulário próprio.
7. Consulte as faturas. Confirme pagamento total ou parcial e a conta usada. As compras continuam classificadas nas categorias; o pagamento da fatura é saída de caixa, sem duplicar consumo.
8. Consulte Futuro financeiro. A projeção considera pendências e recorrências conhecidas. Simular uma compra não cria dívida nem movimenta dinheiro.

## Cadastro simplificado de contas parceladas — correção 0.1.1

1. **Conta:** informe descrição e modalidade. No cartão, escolha o cartão correto. Fora do cartão serve para carnê, boleto, empréstimo ou acordo e não exige cartão nem conta bancária neste momento. Estabelecimento/credor, categoria e responsável ficam disponíveis como informações complementares.
2. **Valores:** escolha expressamente Valor total ou Valor de cada parcela. No primeiro modo, R$ 1.000 em três parcelas resulta em R$ 333,34 + R$ 333,33 + R$ 333,33. No segundo, R$ 333,33 por três parcelas resulta em total R$ 999,99. Informe a quantidade total de parcelas e quantas já foram pagas antes do aplicativo. Zero é válido para parcelas anteriores; a quantidade anterior não pode exceder o total.
3. **Vencimentos e conferência:** fora do cartão, informe a data da primeira parcela, incluindo as já pagas em dívidas anteriores. No cartão, informe o mês da primeira fatura; o dia vem do cartão e o cronograma respeita faturas já ajustadas. Confira total, valores e datas individuais, quantidade paga/restante, saldo devedor inicial, modalidade e último vencimento. Só então confirme.

O preenchimento aceita `1.000`, `1.000,00`, `1000,00` e `333,33`. Agrupamentos inválidos e mais de dois centavos são recusados. O cronograma destaca diferenças de centavos. Este cadastro não movimenta caixa: parcelas anteriores são liquidações históricas; novos pagamentos são confirmados depois nas telas de faturas ou vencimentos.

Erros aparecem junto aos campos e mantêm o preenchimento. Se outro acesso alterar o espaço, confira novamente as parcelas antes de salvar. Se a resposta se perder após a confirmação, use o mesmo formulário para repetir: a chave da operação evita uma segunda dívida. Antes de abrir outro cadastro, atualize e confira a lista para não criar manualmente uma segunda operação independente.

Uma atualização desta correção exige reiniciar o servidor e recarregar a página; não exige migration, limpeza ou reinicialização do banco. Não altere ou remova registros antigos para aplicar a atualização. Vencimentos explícitos legados e ajustes existentes de faturas são preservados.

## Confirmar pagamentos — melhoria 0.1.2

1. Na lista ou nos detalhes da dívida, use **Confirmar pagamento** na parcela pendente. O saldo vem preenchido automaticamente; não é necessário digitá-lo. Confira descrição, número da parcela, conta de pagamento e data (inicialmente hoje, editável até hoje). Uma conta vinculada ativa pode ser sugerida; sem preferência válida, selecione a conta explicitamente.
2. Confira a prévia: valor original da parcela e da compra em campos distintos, valor liquidado, saldo restante, dívida da compra e do espaço e saldo da conta antes/depois. Use **Confirmar pagamento de R$ X**. A confirmação atualiza as telas e os saldos sem recarregamento manual.
3. Para pagar menos, escolha **Alterar valor / pagamento parcial**. Informe um valor positivo até o saldo pendente, em formato brasileiro. O restante continua em aberto e a parcela mostra **Parcialmente paga**, com atraso indicado separadamente quando existir. Na próxima confirmação integral, somente o restante será usado. A dívida só fica quitada quando todas as obrigações estiverem liquidadas.
4. No cartão, a ação é **Pagar fatura**. O valor preenchido corresponde ao saldo da fatura completa, que pode conter outras compras. A prévia mostra quanto será alocado a cada compra/parcela. A ordem é vencimento, data da compra mais antiga, número da parcela e identificador estável em caso de empate. A operação usa uma única conta; o pagamento não cria consumo novamente.
5. Para uma obrigação de mês posterior ao mês da data do pagamento, escolha expressamente **Antecipar pagamento** e confira novamente. A ação usa a operação própria de antecipação e preserva o histórico. Pagar uma fatura do mês corrente antes do dia do vencimento continua sendo pagamento comum. Descontos/encargos contratuais exigem ajuste específico com motivo; não são presumidos.
6. Para corrigir uma confirmação, abra o detalhe da dívida ou fatura, encontre o pagamento e use **Estornar**. Informe o motivo e confirme. O histórico original continua visível como estornado; o caixa recebe o movimento inverso e a dívida é reaberta no valor correspondente. Em faturas com várias compras, cada alocação aparece como uma confirmação e seu estorno alcança somente aquela alocação; confira todas as confirmações se precisar desfazer o pagamento inteiro.

Exemplo sem ajustes: compra de R$ 1.000,00 e pagamento parcial de R$ 150,00 deixam **Valor original R$ 1.000,00**, **Valor liquidado R$ 150,00** e **Saldo devedor R$ 850,00**. Parcelas anteriormente pagas, informadas no cadastro, continuam compondo o valor liquidado sem gerar uma saída nova no caixa.

O botão fica desabilitado durante a confirmação. Erros preservam o preenchimento e não mostram quitação. Se a resposta se perder, repita pelo mesmo formulário: ele mantém a chave da operação. Se outro acesso alterar o espaço, use **Conferir novamente** e revise os valores antes de confirmar; o servidor rejeita a revisão antiga. Administradores e colaboradores podem confirmar/estornar; leitores apenas consultam. Nenhum pagamento histórico é recalculado automaticamente.

Esta atualização exige reiniciar o servidor e recarregar a página, sem migração ou limpeza de banco. O iniciador local permanece o mesmo.

## Conceitos que evitam confusão

- Saldo disponível: saldo inicial mais entradas e saídas efetivamente confirmadas. Limite de cartão não compõe dinheiro disponível.
- Saldo devedor: obrigações de despesas ainda não liquidadas, incluindo parcelas futuras de compras já feitas. As estimativas futuras de recorrências não alteram a dívida atual conforme o horizonte exibido.
- Compromisso mensal: pagamentos ainda previstos naquele mês. A queda no compromisso após a última parcela é uma previsão de calendário; não confirma quitação.
- Atraso: uma obrigação continua pendente depois do vencimento. Valores atrasados são carregados para o mês atual da projeção.
- Relatórios: a classificação de consumo usa a base indicada de compra ou competência. Caixa considera confirmações de pagamento/recebimento. Transferências próprias não compõem receitas e despesas.
- Parcelas: a divisão distribui os centavos restantes nas primeiras parcelas, preservando exatamente o total. Datas com dia inexistente usam o último dia daquele mês e retomam o dia original nos meses seguintes.
- Cartões: compra no dia do fechamento entra na fatura que fecha naquele dia. O vencimento é no mesmo mês se o dia vencer depois do fechamento; caso contrário, no seguinte. Correções de processamento são feitas por fatura. Limite estimado = limite informado menos parcelas pendentes; não é dado bancário confirmado.
- Antecipação: pode confirmar parcelas futuras com a data real do pagamento e registrar desconto/encargo com motivo. Não há cálculo contratual automático de juros nem simulação de oferta de quitação do banco.

## Uso em casal e família

Cada participante cria seu próprio acesso no mesmo servidor. O administrador informa o usuário exato em Configurações e escolhe administrador, colaborador ou leitor. Não há envio de convite por e-mail nesta versão. Leitores consultam e simulam; colaboradores registram movimentações; administradores também gerenciam participantes. O último administrador não pode ser removido. Remover alguém revoga o acesso ao espaço, preservando o histórico.

Todos os membros autorizados veem o mesmo espaço. Dados privados precisam de outro espaço. Um usuário pode participar de vários espaços. Autoria, responsável pelo gasto e pessoa que pagou são informações separadas. Não há divisão automática de despesas nem acerto de valores entre pessoas.

## Backup e restauração

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe tools\backup.py backup --source data/finance.sqlite3 --output backups/finance-AAAA-MM-DD.sqlite3
.\.venv\Scripts\python.exe tools\backup.py verify --source backups/finance-AAAA-MM-DD.sqlite3
.\.venv\Scripts\python.exe tools\backup.py restore --source backups/finance-AAAA-MM-DD.sqlite3 --output data/restaurado-AAAA-MM-DD.sqlite3
```

Sempre escolha um nome novo; a ferramenta recusa sobrescrever arquivos. A origem permanece preservada. O backup usa a API SQLite e valida integridade, referências e documentos financeiros. Inclui usuários, hashes de senhas, associações, sessões e histórico: proteja-o como dado financeiro sensível. Os backups desta máquina ainda não protegem contra perda da própria máquina. Cópia externa cifrada e frequência dependem de destino aprovado; nenhum envio externo foi configurado.

Para validar restauração sem tocar no banco de uso, execute `.\.venv\Scripts\python.exe tools\verify_restore.py`. Esse ensaio cria dados fictícios em test-results, copia e restaura o banco e testa login e saldo em outro processo. Para adotar um banco restaurado, pare o aplicativo, preserve o banco anterior e configure `APP_DB_PATH` no `.env` para o novo arquivo dentro deste projeto. Reabra e confira usuários, contas e saldos. Sessões podem ser encerradas quando a chave secreta muda; o login continua usando as senhas existentes.

## Manutenção e limites atuais

Execute os testes com `.\.venv\Scripts\python.exe manage.py test finance --verbosity 1`. Confira migrações com `manage.py makemigrations --check --dry-run` e configuração com `manage.py check`. Os testes de navegador e suas dependências ficam separados em requirements-dev.txt. Para reproduzir o ensaio visual, na raiz exclusiva:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location).Path '.browser-cache'
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tools\verify_ui.py
```

O teste específico de parcelamentos usa `.\.venv\Scripts\python.exe tools\verify_installments.py`, com base fictícia e servidor temporário em localhost:8767. A leitura monetária é verificada por `node tools/test_finance_input.cjs`. Evidências específicas ficam em test-results/installments-ui-evidence.json. Nenhum desses testes grava na base de uso.

Os pagamentos têm ensaio de interface em `.\.venv\Scripts\python.exe tools\verify_payments.py` (localhost:8769) e concorrência HTTP real em `.\.venv\Scripts\python.exe tools\verify_payments_concurrency.py` (localhost:8770). Ambos criam bases fictícias separadas e encerram seus servidores. Evidências: test-results/payments-ui-evidence.json, payments-concurrency-evidence.json e capturas payments-*.png.

O ensaio cria banco fictício separado e servidor temporário em localhost:8766, encerrado ao terminar. Capturas e resultados ficam em test-results. Verifica o fluxo central, projeção de 12/60 meses, simulação sem persistência e segunda sessão com emulação móvel. Não usa nem altera a base de uso. Atualize versões somente após backup e testes. Nunca grave `.env`, `data`, `backups` ou arquivos de sessão no Git.

A instalação como aplicativo depende do navegador; esta versão não oferece edição offline. O servidor atual aceita somente localhost. Acesso real de outro aparelho e pela internet exige hospedagem aprovada e HTTPS. Duas sessões e a restauração são ensaios técnicos; não substituem a homologação de Hugo e da família em aparelhos reais.

Não há integração bancária/Open Finance, aplicativos nativos, investimentos, contabilidade empresarial, WhatsApp, push, recuperação de senha por e-mail ou auditoria externa inviolável. A recuperação administrativa local pode usar `manage.py changepassword USUARIO` na raiz do projeto. O documento financeiro por espaço é adequado à escala inicial; relatórios muito grandes, múltiplos servidores e RLS independente exigem evolução de armazenamento. O estado atual e o backlog registram os itens ainda pendentes.
