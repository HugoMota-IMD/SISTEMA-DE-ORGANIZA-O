# Estado atual — Sistema de Organização Financeira

Última atualização em **11/11/2026**. Candidata **0.2.0-prep**, preparação local do piloto Render + Neon. Instalação e SQLite oficiais preservados em C:. As roles existentes `organiza_app` e `organiza_migrator`, com logins diretos confirmados por Hugo em 10/11, foram reutilizadas como referência; nenhuma role ou senha foi alterada no Neon. Configuração vigente, mapa de segredos e sequência de aprovação: [PILOT-RENDER-CONFIG.md](PILOT-RENDER-CONFIG.md).

Hugo informou Neon `cool-flower-27024914`, `production/neondb`, São Paulo, e Render **My Workspace / Python 3 / Free / Virginia (US East)**. Após tornar o Git privado, Hugo autorizou explicitamente sincronizar a versão testada com `main`, sem deploy. O conector autenticado como `HugoMota-IMD` confirmou `visibility: private`, permissão de escrita e a base `9b0b470fb2f38b127408fcd0913a93bc3684f0b1`. Esta revisão reúne a candidata completa e preserva o workflow e o registro de importação existentes. [Registro do envio](SYNC-MAIN-2026-11-11.md). Migração no Neon, dados reais e publicação continuam pendentes.

## Retomada do piloto — 11/11

O Web Service agora recebe **somente** a URI pooled de `organiza_app` e o segredo Django. `DATABASE_URL_UNPOOLED` fica no cofre e no processo de manutenção aprovado, fora do Render web e de seus grupos de ambiente. Build/start não executam migrações. O start faz conferência somente leitura da role, dos privilégios e do esquema previamente preparado, depois inicia Gunicorn. Migração explícita: `python tools/migrate_schema.py --render-roles`, com as duas conexões somente naquele processo, usando o mesmo commit aprovado para publicar. A migração 0005 impede importação privilegiada pela role web.

Manifesto ajustado para `main`, `virginia`, Free, uma instância, deploy automático desligado, cadastro por aprovação e manutenção inicial. Campos exatos: raiz vazia, `bash build.sh`, `bash start-render.sh`, `/api/health`. Não cadastrar `DATABASE_URL_UNPOOLED`, `APP_USE_DIRECT_DATABASE` ou owner no serviço.

Laboratório Linux isolado: PostgreSQL e pg_dump 18.6, PgBouncer 1.26.1, TLS com CA fictícia verificada. A suíte Django completa, importações fictícias atual/legada, restaurações cifradas e troca entre instalações web passaram. Pool transacional com uma conexão comprovou reutilização do mesmo backend por quatro clientes, limpeza de ator após commit/rollback/savepoint, permissões e separação de espaços. Build e start reais no Linux passaram; Gunicorn principal e worker sem credencial de migração. Evidências detalhadas e versão final de Python: `test-results/pilot18-evidence.json` e [relatório técnico](REPORT-V0.2-NEON-RENDER.md).

Limites: esses ensaios foram locais, sem escrita ou autenticação no Neon pelo agente e sem publicação no Render. As evidências do Neon continuam sendo os logins diretos assistidos de 10/11. Pool Neon, objetos/privilégios do esquema remoto, TLS público, latência, suspensão/retomada e homologação com computador-base desligado continuam pendentes. O executável Windows pg_dump 17 anterior foi preservado; para o servidor 18, usar ferramenta 18 em executor aprovado, como a do laboratório.

**Próxima ação:** após conferir o commit resultante em `main` e seu CI, validar seleção/titular/cotas do Render e preparar a aprovação final do esquema Neon, eventual corte/importação e implantação manual. Não clicar em Deploy nesta etapa. Nenhum reinício ou migração é necessário na instalação local. `APP_SECRET_KEY` foi gerada localmente e Hugo informou tê-la colado no Render; o segredo não pertence ao repositório. Hugo optou por continuar sem a troca adicional de senha sugerida após uma captura; nenhuma senha foi redefinida pelo agente.

Os registros abaixo são históricos e não substituem o procedimento de 11/11.

## Configuração assistida de senhas Neon — 10/11

**Ponto de retomada para 11/11/2026, a pedido de Hugo:** encerrar a sessão após registrar a conclusão. As senhas de `organiza_app` e `organiza_migrator` foram configuradas e os dois logins diretos estão confirmados. Não recriar roles nem repetir a configuração de senhas. Na retomada, preparar as URIs no cofre (aplicação pooled; migrator direta), conferir o Git privado exclusivo e o workspace Render, validar pooling e alinhar ferramentas/ensaios com PostgreSQL 18.6. Publicação e importação real continuam condicionadas à aprovação final. Nenhuma credencial está neste registro.

As capturas de Hugo confirmam `organiza_app` e `organiza_migrator` existentes, LOGIN habilitado, indicadores administrativos consultados desabilitados, ausência de associações a outras roles, CONNECT/USAGE para ambas, CREATE em `public` apenas para a migrator e ausência de CREATE/TEMP no banco. A sessão administrativa conectou por TLS 1.3 a `neondb` como `neondb_owner`; o servidor exibido é **PostgreSQL 18.6**. Essas evidências são do operador, sem autenticação do agente no Neon.

A orientação anterior de usar `psql \password` foi corrigida: o provedor rejeitou o hash gerado no cliente com HTTP 400, exigindo senha original em SQL via TLS. Naquela tentativa, nenhuma senha das duas roles foi confirmada. Foi preparado `tools/set_neon_role_passwords.py`, com prompts ocultos, destino fixo, revalidação das duas roles, alteração apenas das senhas, TLS verificado, novas conexões de teste por role e supressão de erros que poderiam conter segredos. O programa não promete atomicidade entre as duas alterações nem ausência de logs internos no provedor. Dez testes offline em `tools/test_neon_role_passwords.py` passaram. Não foram alterados o banco local, pagamentos, esquema ou dados reais.

Nova captura: uma execução parou por reutilização de senha e outra por erro genérico antes de enviar alteração. O utilitário recebeu o modo `--check-admin`, somente leitura, que pede apenas a senha administrativa atual e diagnostica conexão/identidade/permissões. Códigos sanitizados e etapa da falha substituem a mensagem genérica; nenhuma mensagem bruta do servidor ou senha é impressa. **15 testes offline passaram**, além da recusa real de stdin redirecionado. O agente verificou somente o handshake TLS 1.3 e o certificado do endpoint, sem autenticação, SQL ou alterações.

**Conclusão por Hugo:** o diagnóstico identificou recusa da senha administrativa. Após informar a senha atual, a captura `codex-clipboard-0411b33a-ae13-4f10-8de6-c620002bb0be.png` mostrou `DIAGNOSTICO_OK`. Hugo executou então o modo normal e confirmou a conclusão; a captura `codex-clipboard-09bc6a8b-4237-4872-bc15-14a9ae6e12ed.png` mostra que as duas senhas foram alteradas e ambos os logins diretos foram verificados. A evidência é a execução do operador com o utilitário local, não uma autenticação do agente. Nenhuma credencial foi recebida ou persistida nesta conclusão. A ferramenta não alterou tabelas, concessões, migrações ou dados financeiros. Não repetir o modo de configuração de senhas sem intenção de rotacioná-las.

Próxima ação: preparar no cofre `DATABASE_URL` de `organiza_app` com pooling ligado e `DATABASE_URL_UNPOOLED` de `organiza_migrator` com pooling desligado, mantendo o mesmo banco/branch e SSL. O login pooled, o esquema da aplicação e a execução hospedada ainda não foram verificados. Confirmar a URL do Git privado exclusivo e o workspace Render antes de cadastrar no serviço aprovado e publicar. Detalhes em [NEON-ROLES-RENDER.md](NEON-ROLES-RENDER.md). Antes do corte, alinhar as ferramentas de backup e validar PostgreSQL 18; os testes anteriores em 17.11 não comprovam restauração no servidor 18. Publicação e importação real mantêm a aprovação final pendente.

## Preparação de 09/11 em C:

O manifesto prevê um serviço Django Free e publicação manual. O iniciador exige PostgreSQL, conexão direta para esquema e cadastro por aprovação ou fechado. O piloto começa em consulta. A administração técnica de contas, os membros de cada espaço e as validações de autoria/transação foram exercitados nos dois bancos.

Passaram 180 testes em PostgreSQL 17.11 e 170 em SQLite, com dez pulos próprios de PostgreSQL. Dois ensaios de migração e recuperação cifrada usaram exclusivamente dados fictícios, inclusive uma origem no esquema 0002 da V0.1.3. Duas instalações web independentes preservaram sessão, saldos, histórico e projeções. Passaram ainda cinco grupos de implantação, doze testes das ferramentas e cinco grupos de acesso em navegador. O backup da base de uso foi restaurado à parte e comparado em conteúdo.

O Git local continua em `main`, sem commit ou remoto. Hugo deve identificar o repositório privado específico e o workspace Render Hobby. O projeto Neon indicado por Hugo aguarda conferência autenticada de recursos existentes. Publicação, migração real, backup externo e homologação com o computador-base desligado dependem das respectivas aprovações. [Relatório completo ao COMANDO MESTRE](REPORT-V0.2-NEON-RENDER.md) · [Próximos passos e procedimento de retorno](HOSTING-NEON-RENDER.md)

## Histórico de 29/10 — instalação das skills Neon

Hugo informou a decisão de migrar a hospedagem para **Neon + Render**. Nesta rodada foi executado o comando solicitado **`npx neon skills -y`**, com CLI Neon **8.13.2** e Node **24.16.0**, confirmado na [documentação oficial](https://neon.com/docs/cli/skills). A instalação terminou com sucesso no escopo deste projeto, para o agente **Codex**, sem instalação global.

Foram instaladas nove skills oficiais de `neondatabase/agent-skills` em `.agents/skills`: neon, neon-postgres, neon-postgres-branches, neon-postgres-egress-optimizer, neon-auth, neon-ai-gateway, neon-functions, neon-object-storage e neon-realtime. O instalador criou `skills-lock.json`; todos os nove SKILL.md foram verificados. A disponibilidade para o Codex ocorre no próximo turno.

Esta etapa instalou orientação de desenvolvimento; **não migrou dados, não criou serviços Neon/Render e não alterou a autenticação Django ou a hospedagem em operação**. As assinaturas de AGENTS.md, config/settings.py e do banco oficial permaneceram idênticas antes/depois. Não houve autenticação cloud, credencial gravada, deploy, push ou escrita no Drive. Evidência local ignorada: `test-results/neon-skills-installed.json`.

A preparação de Django/PostgreSQL planejada nesta data foi concluída em 09/11, conforme o registro acima.

## Histórico de 29/10 — acesso privado Tailscale

Google Cloud adiado conforme comando de Hugo. Servidor identificado como **DESKTOP-FLDE4SK**, IP Tailscale confirmado **100.108.133.59**, cliente 1.104.4 conectado e MagicDNS ativo. O iPhone aparecia online na rede, sem comprovar acesso ao aplicativo. Os outros dois computadores ainda precisam entrar na tailnet autorizada e homologar o acesso.

A unidade D: e a raiz nova informada não estão disponíveis nesta máquina. A aplicação existente, a raiz Git e o banco configurado foram efetivamente confirmados em `C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`, com banco `data\finance.sqlite3`. A versão anterior era 0.1.2 e o processo estava parado. Nenhuma instalação vazia foi criada. Backup SQLite consistente e verificado foi realizado antes das alterações em `backups/finance-before-tailscale-20261029-135121.sqlite3`.

Backend permanece **127.0.0.1:8765**. Endereço privado ativo: **https://desktop-flde4sk.tail08d4d6.ts.net/**, via Serve HTTPS 443 → 127.0.0.1:8765. Host/CSRF exatos, proxy Waitress confiando somente no protocolo encaminhado por loopback e cookies privados Secure com nomes próprios; o HTTP local continua compatível. Autenticação individual, perfis, espaços e motor financeiro preservados. Nenhuma migração de banco.

**Bloqueio inicial resolvido:** primeiro o Tailscale retornou “Serve is not enabled on your tailnet.”. Hugo depois mostrou a tela **“Serve está pronto para usar”**, com Funnel opcional desmarcado. A nova aplicação da rota foi aceita. O ensaio HTTPS real usou somente a rota temporária 8443 → backend/banco fictício 8771, certificado validado sem bypass e oito grupos aprovados. O backend de teste foi encerrado e apenas a rota 8443 removida; depois foi aplicada e verificada a rota oficial 443. Funnel não foi habilitado. Nenhuma regra de firewall, roteador, energia ou suspensão foi alterada.

Iniciador aprimorado com start/status/stop, locks, identidade da instalação, validação do banco existente, logs locais e recusa de conflito externo. Inicialização automática no logon está preparada como opção reversível HKCU, **desativada**. O processo não solicita elevação administrativa. Ferramenta escopada de configuração do Serve recusa destinos alheios/públicos e nunca usa reset global. Guia operacional: **docs/PRIVATE-ACCESS.md**.

Validações executadas: **134 testes Django aprovados (126 anteriores + 8 de acesso privado)**; oito grupos HTTP e **oito grupos HTTPS real** fictícios, incluindo certificado, cookies Secure/HSTS, login/logout, CSRF, papéis/espaços, pagamentos simultâneos 200/409, reenvio e persistência completa após reinício com mudança de PID; seis grupos do iniciador; 18 testes isolados do helper Serve; 33 verificações monetárias; fluxo geral de navegador e backup/restauração aprovados. O endereço oficial respondeu com a identidade desta instalação, em HTTP e HTTPS, e a tela de login abriu no navegador sem alerta de certificado. Nenhum aparelho físico foi testado.

Oficial iniciado pelo novo iniciador: página HTTP 200, `/api/health` versão **0.1.3**, metadados apontando exatamente para o banco confirmado; segunda execução não duplicou processo. Parada e novo início oficiais também foram conferidos: assinatura SHA-256 do banco idêntica, processo não elevado e bind somente loopback. **18 testes isolados do helper Serve aprovados**. A tentativa anterior à liberação teve limite de tempo e preservou snapshot/configuração vazia; esse bloqueio foi resolvido na ativação descrita acima. Evidências dessa primeira etapa em `test-results/tailscale-preservation-before.json`, `tailscale-preservation-result.json`, `tailscale-private-status.json`, `tailscale-local-status.json`, `private-access-http-evidence.json`, `runtime-evidence.json`, `ui-evidence.json` e `restore-evidence.json`.

Na ativação, um novo backup consistente foi verificado: `backups/finance-before-serve-activation-20261029-160313.sqlite3`. Evidências complementares: `test-results/private-access-https-evidence.json`, `tailscale-active-private-status.json`, `tailscale-activation-before.json` e `tailscale-activation-result.json`. A configuração final contém apenas a rota oficial esperada, sem rota de teste, sem Funnel e sem alterações a outros serviços.

**Próxima ação:** Hugo homologar **https://desktop-flde4sk.tail08d4d6.ts.net/** no iPhone e nos dois computadores, com Tailscale ativo, incluindo dados móveis/outra rede. A liberação administrativa inicial já está resolvida; não é necessário habilitar Funnel. Início automático continua opcional/desativado. Instruções e arquivos desta entrega: **docs/REPORT-V0.1.3-TAILSCALE.md**. Sem publicação pública, push, remoto Git, escrita no Drive ou alteração de outros projetos.

## Melhoria anterior — confirmação de pagamentos 0.1.2

Implementada a confirmação integral pelo saldo pendente, sem redigitar valor, nas listas e nos detalhes das parcelas. O formulário identifica descrição e número da parcela, sugere somente conta vinculada ativa ou exige seleção explícita, permite data até hoje e mostra a prévia antes/depois. A opção secundária habilita pagamento parcial. Os rótulos distinguem valor original da parcela e da compra, valor liquidado e saldo devedor. Sucesso atualiza estado, painel, listas, histórico, faturas e projeção; erros mantêm o formulário e não indicam quitação.

O motor anterior de liquidações, estornos, revisão, idempotência e transação foi reaproveitado e reforçado. Prévia de pagamento é somente de leitura. O servidor valida valor integral/parcial, saldo esperado, revisão, conta, data, pessoa e espaço. Parcela de cartão não pode ser paga diretamente: encaminha para a fatura. A fatura distribui pagamento em ordem de vencimento, compra mais antiga, número da parcela e ID estável, usando uma única conta. Seus registros internos de alocação somam exatamente o valor confirmado, sem novo consumo ou débito adicional pelo total. Estorno continua por pagamento/alocação, com motivo, caixa inverso e preservação do histórico.

Pagamento de despesa de mês posterior ao mês da data efetiva exige a escolha explícita de antecipação, também validada no servidor e registrada como operação própria. Fatura do mês corrente pode ser paga antes do dia do vencimento. Não são presumidos juros, descontos ou encargos. Nenhum pagamento, valor ou data histórico foi modificado automaticamente.

**Validação: 126 testes Python aprovados (97 existentes e 29 novos), 33 verificações monetárias, nove grupos de navegador para pagamentos, nove grupos anteriores de parcelamento e fluxo geral sem erros de console.** Teste HTTP simultâneo com duas sessões reais retornou 200/409, com um pagamento, um débito e repetição da chave vencedora sem duplicação. Falha de gravação injetada reverteu documento, revisão, pagamento, caixa, operação e auditoria. Backup/restauração, configuração, dependências e migrações também passaram.

Computador 1440×1000 e celular emulado 390×844, com capturas inspecionadas; nenhum aparelho físico. Bases fictícias isoladas em todos os ensaios. A assinatura SHA-256 do banco de uso permaneceu idêntica antes/depois, inclusive após reiniciar o servidor. Nenhum banco foi apagado, limpo ou migrado.

A correção anterior 0.1.1 está implementada e suas regressões passaram novamente. Não foi recriado seu formulário. O conflito originalmente relatado por Hugo continua sem mensagem/sequência exatas; os dois defeitos concretos documentados anteriormente permanecem corrigidos, sem atribuir a eles a causa do relato original.

Servidor local reiniciado nesta execução: `/api/session` informou **0.1.2**, página e script retornaram HTTP 200, e a nova confirmação foi identificada no script servido. Logs anteriores preservados. **Não exige migração; Hugo deve recarregar a página.** O servidor continua restrito a localhost e depende do processo local ativo.

Relatório ao COMANDO MESTRE, arquivos e roteiro: **docs/REPORT-V0.1.2-PAYMENTS.md**. Evidências locais: test-results/payments-ui-evidence.json, payments-concurrency-evidence.json, payments-preservation-result.json, payments-local-access.json e capturas payments-*.png. Git continua sem commits/remoto; nenhuma publicação, envio de código, escrita no Drive ou alteração de outro projeto.

## Recuperação do acesso local — 21/10/2026

Hugo informou que o navegador não conseguia acessar `http://127.0.0.1:8765/`. A conexão foi recusada na verificação inicial; o servidor local não estava respondendo. Foi iniciado o processo existente do projeto, restrito a localhost, preservando logs anteriores. A razão pela qual o processo anterior terminou não foi determinada; não se atribuiu a interrupção a reinício da máquina sem evidência.

Validação desta sessão: `/api/session` respondeu com versão 0.1.1, a página inicial e `/static/app.js` retornaram HTTP 200 e o novo formulário de parcelamento foi identificado no arquivo servido. A assinatura do banco permaneceu idêntica durante essas consultas. Nenhum cadastro de teste, migração, reinicialização de banco ou alteração de código financeiro foi realizado. Foram alterados somente este estado e docs/REPORT-2026-10-21-LOCAL-ACCESS.md; logs operacionais gerados permanecem ignorados pelo Git.

A execução depende de o processo local permanecer ativo. Os iniciadores examinados não configuram um serviço permanente nem início automático; para abrir manualmente em outra ocasião, executar start.ps1 na raiz exclusiva, conforme o manual. A próxima ação é recarregar o navegador e continuar a homologação de contas parceladas. Sem publicação, Git remoto ou escrita no Drive.

## Correção anterior — contas parceladas 0.1.1

Hugo relatou conflito na regra de cadastro e pediu simplificação, sem mensagem exata ou sequência completa. Foram reproduzidos dois defeitos específicos nos arquivos anteriores preservados: rejeição do valor brasileiro `1.000` e cartão com vencimento dia 31 passando a usar 28 nos meses seguintes à primeira fatura em fevereiro. Esses cenários foram corrigidos e verificados; não foi demonstrado que correspondem exatamente à ocorrência original de Hugo.

O parcelamento possui agora formulário exclusivo em três etapas: conta/modalidade → valores/vencimentos → cronograma e confirmação. Permite cartão ou fora do cartão, entrada por valor total ou da parcela, parcelas já pagas, prévia exata no servidor e mensagens junto aos campos sem perder o preenchimento. Dívida pendente externa dispensa cartão e conta; pagamento real continua exigindo conta válida. A confirmação fica vinculada à revisão da prévia; conflito exige nova conferência e reenvio após resposta perdida mantém a mesma operação. O cadastro comum não mistura parcelamento com recorrência/transferência/pagamento imediato.

**Validação naquela entrega: 97 testes Python aprovados (71 financeiros + 17 API existentes + 9 novas regressões), 33 verificações monetárias e nove grupos de navegador de parcelamento, além do fluxo geral anterior.** Computador 1440×1000 e celular emulado 390×844; nenhum aparelho físico usado. Migrações e dependências sem divergência. Não é necessária migração de banco; é necessário reiniciar o servidor e recarregar a página.

A base de uso foi inspecionada somente em leitura, sem dados pessoais na saída: havia um espaço e nenhum lançamento parcelado, sem incompletos/duplicados identificados. Nenhum registro foi removido ou corrigido automaticamente. Os testes e a reprodução histórica usaram bases fictícias separadas. Logs foram consultados por extração sanitizada, sem traceback que identificasse o relato específico. A assinatura dos documentos financeiros é comparada antes/depois em evidências locais.

Preservação confirmada: assinatura do arquivo SQLite e dos documentos financeiros idêntica antes/depois, em test-results/installments-preservation-result.json. A restauração completa da suíte anterior foi repetida com sucesso. Servidor local reiniciado e versão 0.1.1/formulário novo confirmados em localhost; logs anteriores preservados. Para Hugo, resta atualizar a página e homologar, sem migração ou limpeza.

Relatório completo, arquivos desta tarefa e roteiro de homologação: **docs/REPORT-V0.1.1-INSTALLMENTS.md**. Evidências: test-results/installments-baseline-evidence.json, installments-ui-evidence.json, installments-integrity-before.json e installments-integrity-after.json. Foram preservados registros existentes, fontes anteriores, Git e logs. Sem commits, push, publicação, implantação ou escrita no Drive.

## Raiz e diagnóstico da implantação inicial

Chat confirmado: `CODEX — ORGANIZAÇÃO FINANCEIRA`. Raiz efetivamente utilizada e raiz Git confirmada:
`C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`.

AGENTS.md, README.md e estado atual foram lidos antes das alterações. Existiam somente documentos iniciais, sem aplicação anterior. O comando V01 recebido de Hugo foi preservado em docs/EXECUTION-COMMAND-V01.txt. O guia do Drive foi consultado pela conta autorizada; nenhuma escrita foi feita no Drive.

## Implementação e decisões

- Django 5.2.18 LTS, Python 3.14.6, SQLite no servidor e Waitress 3.0.2; dependências fixadas.
- Login individual, sessões, CSRF, espaços e papéis administrador/colaborador/leitor. Associação explícita, autorização na API, filtro em SQL, gatilhos de escrita e proteção do último administrador.
- Contas/carteiras, receitas previstas/recebidas, despesas/Pix, transferências, cartões, faturas, parcelas e dívidas anteriores. Pagamentos parciais, estornos, antecipação e ajustes rastreáveis.
- Categorias/subcategorias editáveis, responsáveis e estabelecimentos separados da forma de pagamento; edição descritiva e arquivamento sem reescrever saldos originais.
- Centavos inteiros, obrigações como fonte única de dívida, pagamento de fatura sem duplicar consumo, revisão esperada, idempotência e auditoria.
- Recorrências mensais com valor conhecido e término opcional; edição por ocorrência ou futuras, preservando liquidações.
- Projeção extensível, simulação sem persistência, relatórios mensais por compra/competência com caixa separado, orçamento e alertas internos. Previsões recorrentes futuras não inflam a dívida atual ao ampliar o horizonte.
- Interface responsiva em português, manifesto de instalação, manual e backup/restauração sem sobrescrever arquivos.

Detalhes: docs/ARCHITECTURE.md, FINANCIAL-MODEL.md, REQUIREMENTS.md, BACKLOG.md e ACCEPTANCE.md. O documento financeiro por espaço atende à escala inicial. SQLite não oferece RLS PostgreSQL: o operador do arquivo/banco e dos backups continua privilegiado, conforme documentado.

## Testes da entrega 0.1.2 — histórico

| Verificação | Resultado |
|---|---|
| `manage.py test finance --verbosity 1` | **126/126 aprovados**: 91 regras financeiras, 17 API/segurança, 9 regressões de parcelamento e 9 de pagamentos |
| Dinheiro, parcelas e datas | R$ 285 em Alimentação; R$ 1.000/3 exatos; compromisso outubro R$ 1.000 → novembro R$ 850; atraso sem quitação |
| Integridade financeira | Fatura sem duplicação, parcial, estorno/cancelamento/antecipação, transferência, cartões distintos e dívida anterior aprovados |
| Segurança | Espaços/perfis, CSRF, autoria, idempotência, conflito de revisão, histórico imutável e gatilhos sem ator/outro espaço/leitor aprovados |
| Configuração | `check`, `makemigrations --check --dry-run`, `pip check` e sintaxe JavaScript sem problemas |
| Configuração futura HTTPS | `check --deploy` sem alertas em modo não local com chave efêmera de teste; nenhum serviço publicado |
| Backup/restauração | Snapshot completo idêntico em outro processo, login de administrador e leitor, integridade e recusa de sobrescrita |
| Navegador | Fluxo geral, nove grupos de parcelamento e nove de pagamentos; integral, parcial/restante, fatura, estorno, antecipação, erro preservado, reenvio e perfis; 1440×1000 e 390×844, sem erros de console ou transbordamento |
| Confirmações simultâneas HTTP | Duas sessões autenticadas enviaram a mesma confirmação simultaneamente: 200/409, um pagamento e um débito, reenvio da vencedora sem duplicação |

O ensaio de restauração inclui 2 usuários, 2 contas, 1 cartão, 8 lançamentos, 9 obrigações, 3 pagamentos, 5 movimentos de caixa, recorrência, orçamento, 12 eventos de auditoria e projeção de 12 meses. Saldo 153456 centavos e dívida 92000 centavos foram preservados. Os dados são fictícios.

Evidências locais ignoradas pelo Git: test-results/ui-evidence.json, restore-evidence.json e capturas ui-login-desktop.png, ui-home-desktop.png, ui-home-mobile.png, ui-future-desktop.png e ui-future-mobile.png. Nenhum aparelho físico foi testado. O banco de uso data/finance.sqlite3 foi originalmente entregue vazio; o espaço cadastrado posteriormente foi preservado nesta correção.

## Limites, arquivos e Git

Backend limitado a `127.0.0.1:8765`, com acesso HTTPS privado ativo pelo Tailscale Serve. Homologação nos aparelhos físicos e por outra rede permanece pendente. Início automático no logon é opção preparada/desativada; não há serviço independente de logon. Duas sessões e emulação móvel não equivalem a teste em aparelhos reais. Não há edição offline, integração bancária, push, WhatsApp, aplicativo nativo ou juros contratuais automáticos.

Ainda sem ação dedicada para encerrar recorrência já criada, divisão/acerto automático familiar, recuperação de senha por e-mail, exportação de relatórios ou intervalo arbitrário de datas. Reembolso já devolvido pode exigir correção específica em vez de estorno integral. Relatórios reclassificam ajustes na base da compra e preservam o histórico, sem contabilidade bitemporal. Backup externo cifrado depende de destino aprovado.

Arquivos da entrega inicial: docs/REPORT-V0.1.md; cadastro: docs/REPORT-V0.1.1-INSTALLMENTS.md; pagamentos: docs/REPORT-V0.1.2-PAYMENTS.md; preparação privada atual: docs/REPORT-V0.1.3-TAILSCALE.md. AGENTS.md preservado sem alteração. `.venv`, `.browser-cache`, data, backups e test-results ignorados. Git iniciado, ainda sem commits e sem remoto. Não houve commit, push, criação de remoto ou publicação pública. Nenhum arquivo de outro projeto foi alterado ou descartado.

## Próxima ação

Preparar a migração Neon + Render com banco de teste e preservar o ambiente oficial em operação até validar a transferência. A instalação das skills está concluída; a migração ainda não foi executada. A homologação do acesso privado nos três dispositivos e por outra rede continua pendente, conforme docs/PRIVATE-ACCESS.md. Se reaparecer o conflito anterior no cadastro, registrar mensagem, modalidade e etapa. Google Cloud continua adiado; nenhum remoto Git, push ou escrita no Drive foi realizado nesta etapa.
