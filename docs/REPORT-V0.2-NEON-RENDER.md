# COMANDO MESTRE — Organiza — preparação para Neon e Render

**Atualização de sincronização, 11/11:** Hugo tornou o repositório privado e autorizou o envio da candidata testada para `main`, sem deploy. Privacidade, identidade e permissão de escrita foram reconfirmadas. Esta revisão preserva o histórico e o workflow remoto, incorpora a preparação integral e mantém banco/segredos fora do Git. Ver [SYNC-MAIN-2026-11-11.md](SYNC-MAIN-2026-11-11.md). As referências abaixo a Git público e envio ainda não autorizado descrevem a etapa anterior. Esquema Neon, importação real e publicação continuam sem execução/autorização final.

## Retomada de 11/11/2026 — configuração preparada, publicação pendente

Preparação executada exclusivamente no Organiza, preservando a instalação e o SQLite em C:. Nenhum push, deploy, escrita no Drive, importação real ou alteração de roles/senhas do Neon. Os procedimentos desta seção e de [PILOT-RENDER-CONFIG.md](PILOT-RENDER-CONFIG.md) substituem as orientações históricas abaixo sobre migração durante a partida.

**GitHub verificado.** `HugoMota-IMD/SISTEMA-DE-ORGANIZA-O` contém o Organiza, mas permanece **público**. `main`: `9b0b470fb2f38b127408fcd0913a93bc3684f0b1`, de 03/11. Dos 70 arquivos comuns, 53 coincidem e 17 diferem da candidata local. Faltam no remoto a migração 0005, ferramentas de roles/verificação e documentação atual, entre outros. O workflow e o registro de importação exclusivos do remoto devem ser preservados no envio autorizado. Checkout local sem primeiro commit/remoto. **Ainda não existe commit remoto aprovado da candidata completa.** Não usar `9b0b470` para esta implantação.

**Decisão de credenciais.** O Web Service usa apenas `DATABASE_URL` pooled de `organiza_app`. `DATABASE_URL_UNPOOLED` direta de `organiza_migrator` fica no cofre/processo isolado de manutenção, nunca no web ou grupo de ambiente vinculado. Build/start deixaram de aplicar esquema e removem defensivamente variáveis de manutenção herdadas. O novo verificador web confere identidade, privilégios, tabelas e proteção de importação em transação somente leitura. Depois inicia Gunicorn. A operação `python tools/migrate_schema.py --render-roles` continua preparada para execução explícita e aprovada fora do Render, usando o mesmo commit da publicação. O Free não depende de pre-deploy command ou Shell para esse fluxo.

**Render preparado.** My Workspace, Python 3, Free, Virginia (US East), uma instância; branch `main` no futuro SHA aprovado; Root Directory vazio; Build `bash build.sh`; Start `bash start-render.sh`; Health `/api/health`; Auto-Deploy Off. `PYTHON_VERSION=3.14.6`, `APP_ENVIRONMENT=production`, `APP_LOCAL_MODE=false`, `APP_DEBUG=false`, `APP_REGISTRATION_MODE=approval`, `APP_READ_ONLY=true`. Segredos do serviço: somente `DATABASE_URL` e `APP_SECRET_KEY`. O Render fornece `PORT` e `RENDER_EXTERNAL_HOSTNAME`. Valores e procedimento de cadastro: [mapa completo](PILOT-RENDER-CONFIG.md). O workspace/plano/cotas são informações de Hugo ainda não conferidas no painel pelo agente.

### Testes reais de 11/11

Laboratório Linux Docker sem rede externa, sem portas publicadas e sem montagem de arquivos do host. Contexto de build com código permitido, sem `.env`, banco oficial ou backups. PostgreSQL/pg_dump **18.6**, PgBouncer **1.26.1**, Python **3.14.6**, Django **5.2.18**, Psycopg **3.3.6**, Gunicorn **26.2.0**. Certificados e senhas fictícios gerados no container; TLS verificado. Serviços internos encerrados ao fim, container com código de saída zero.

| Verificação | Resultado |
| --- | --- |
| `python manage.py test finance --noinput -v 1` em PostgreSQL 18.6 | **180 aprovados**, sem pulos; inclui regras financeiras, parcelas/pagamentos, permissões, transações, concorrência e segurança hospedada |
| `python -m unittest tools.test_postgres_tools tools.test_neon_role_passwords -v` | **28 aprovados**: 13 de gestão e 15 do helper de senhas; testes offline, sem redefinir senhas reais |
| Importação fictícia atual e legada, por migrator sem propriedade do banco | Dois ensaios aprovados; conciliação de registros, sessões, valores/projeções, reenvio e rollback de falha |
| Backup e restauração com ferramentas 18.6 | Dois dumps cifrados restaurados em bancos separados; conteúdo/sequências iguais, chave errada/corrupção/destino ocupado recusados |
| Duas instalações HTTP, role web sem propriedade | Cadastro por aprovação, participantes, pagamento, nova sessão do processo e persistência de sessão/saldo/histórico/projeção aprovados |
| PgBouncer transacional, uma conexão de servidor | Quatro clientes independentes usaram **um mesmo PID PostgreSQL**; ator limpo após commit, rollback e savepoint; importação privilegiada recusada à app |
| HTTP/SQL pelo pool | Admin/colaborador permitidos; leitor sem escrita; outro espaço sem leitura/escrita; 4 clientes concorrentes e 16 leituras. Escritas concorrentes: admin **200**, colaborador **409**, leitor **403**, externo **404**. A corrida entre escritores pode inverter o vencedor |
| Privilégios efetivos pelo pool | Recusados DDL, `SET ROLE` migrator, TRUNCATE, edição do histórico e elevação de superusuário; revisão do espaço externo permaneceu zero |
| Migração separada e pacote Render | `migrate_schema.py --render-roles` aprovado no banco fictício; **5 grupos** do pacote; build Linux real com pip/check/collectstatic aprovado |
| `bash start-render.sh` e Gunicorn reais em Linux | Saúde HTTP 200 com proxy HTTPS simulado; principal e worker sem `DATABASE_URL_UNPOOLED`; contagem de migrações inalterada durante a partida |

Evidências desta rodada: `test-results/pilot18-evidence.json`, `test-results/pilot-pooling-evidence.json` e logs/JSON em **`test-results/pilot18-20261111/`**. Evidências antigas 17.11 foram preservadas em seus locais anteriores. A primeira montagem do laboratório exigiu correção da CA explícita do PgBouncer e de um nome de função no próprio runner; a execução final completa acima passou. Nenhuma falha de isolamento do aplicativo foi reproduzida nesses cenários.

**Preservação.** SHA-256 do SQLite original antes/depois: `7735814E8FAD0FA8A7F385987331D461FAD3332D7226703D72BC2CFD7E961E40`. `.env`, usuários, pagamentos, backups e configuração do serviço local não foram alterados. Não é necessário reiniciar ou aplicar migração na instalação local. As ferramentas Windows PostgreSQL 17 foram mantidas; usar ferramentas 18 no executor aprovado para exportar/restaurar o Neon 18. A imagem do laboratório inclui a versão compatível, sem instalar outro servidor no Windows.

### Arquivos alterados nesta rodada

| Finalidade | Arquivos |
| --- | --- |
| Serviço e segredos | `build.sh`, `start-render.sh`, `render.yaml`, `.env.example`, novo `tools/check_runtime_database.py` |
| Regressão e laboratório | `tools/verify_deployment_preparation.py`, novos `tools/verify_pilot_lab.py`, `deploy/pilot-lab.Dockerfile`, `.dockerignore` |
| Documentação/estado | `README.md`, `docs/CURRENT-STATE.md`, `docs/NEON-ROLES-RENDER.md`, `docs/HOSTING-NEON-RENDER.md`, este relatório e novo `docs/PILOT-RENDER-CONFIG.md` |

### Limites, pendências e próxima ação

Os ensaios acima são **locais**, não testes no Neon ou Render. No Neon, a evidência disponível continua sendo a conclusão assistida de Hugo em 10/11: logins diretos das duas roles confirmados. Pool real, conteúdo/ownership do esquema, concessões após migração e execução do aplicativo nesse provedor aguardam a janela aprovada. O banco de produção não recebeu escrita de ensaio. Nenhum recurso Neon foi recriado.

O isolamento de leitura é aplicado pela autorização/filtros do Django; os gatilhos reforçam escrita/autoria/revisão. Não se trata de RLS independente para cada participante. A role web deve permanecer secreta e confiável. HTTPS público, suspensão/retomada Render Free, latência Virginia–São Paulo, redeploy e acesso com o computador-base desligado permanecem sem homologação. Backup externo segue inativo.

**Próxima ação objetiva para Hugo:** conferir a visibilidade Private do repositório indicado e My Workspace/Free/Virginia, titular e cotas no painel. Depois aprovar o envio da candidata, registrar e validar o novo SHA e apresentar a aprovação final do esquema/corte/publicação. O roteiro está pronto no mapa de configuração; não há razão para redefinir senhas novamente. A liberação de escrita exige `APP_READ_ONLY=false` apenas após reconciliação aprovada, pois o modo inicial também bloqueia login.

---

## Histórico — preparação e configuração assistida até 10/11

**Complemento de 10/11/2026.** A `main` encontrada na conferência anterior do GitHub era pública e diferia da candidata. As roles separadas passaram nos ensaios locais; Hugo concluiu também a definição das senhas e a verificação de ambos os logins diretos no Neon. Conexão pooled, migração e publicação seguem pendentes. O procedimento e o ponto de retomada estão no [complemento de roles e implantação](NEON-ROLES-RENDER.md) e no [estado atual](CURRENT-STATE.md). Os resultados a seguir registram a etapa de 09/11.

**09/11/2026 · Candidata 0.2.0-prep · Etapa local concluída.** A instalação oficial e o banco permanecem em C:. O serviço hospedado aguarda a identificação do Git privado, do workspace Render e a aprovação final. A versão 0.1.3 é a última homologação técnica local registrada. Nesta retomada, a porta 8765 estava sem servidor e o Tailscale Serve continuava apontando para ela em modo privado.

## Entrega

- Um serviço web Django preparado para Render Free, com Gunicorn, arquivos estáticos coletados pelo WhiteNoise, HTTPS atrás do proxy, CSRF, cookies seguros e logs sanitizados. O build valida dependências e a configuração de produção. O iniciador confere as conexões antes de aplicar o esquema pela URL direta. A aplicação exige PostgreSQL com TLS verificado. A falta da URL, SQLite e cadastro público aberto impedem a inicialização.
- O piloto começa em manutenção. A aplicação recusa gravações HTTP e deixa a saúde do processo disponível sem consultar o banco. A reabertura exige o valor explícito `APP_READ_ONLY=false`. O iniciador Windows e os testes com caminho SQLite recusam configurações conflitantes com PostgreSQL.
- Contas individuais continuam no Django. Uma solicitação de acesso recebe HTTP 202, cria conta inativa e aguarda aprovação. A administração técnica pode ativar ou bloquear contas e registra a autoria. **Configurações → Participantes** apresenta usuários do espaço, identificadores, papéis e situação. A listagem global requer superusuário. Há limitação de tentativas de login e proteção ao último administrador.
- Em PostgreSQL, os gatilhos validam autoria, associação, revisão e histórico, com o ator definido por transação. A migração preserva a origem, compara vínculos, valores e projeções antes de confirmar e registra recibo contra reimportação. O backup usa `pg_dump` custom + age, checksum e restauração transacional em outro banco vazio.
- O backup externo está preparado como **modelo inativo** para um executor independente do Render e do computador de Hugo. A rotina passa a receber uma chave pública age, e a identidade de decifragem fica em cofre separado. A ativação exige confirmação da conta e da pasta do Drive e recuperação a partir de um arquivo efetivamente transferido.

## Verificado localmente com dados fictícios

| Verificação | Resultado | Evidência dentro de `test-results/` |
| --- | --- | --- |
| Suíte Django completa em PostgreSQL 17.11 | **180 de 180 aprovados**, sem pulos. Inclui permissões, isolamento entre espaços, acesso técnico, cadastro, parcelas, pagamentos, revisões e falhas de transação. | `resume-fullpg.log` |
| Suíte Django completa em SQLite | **170 aprovados**, 10 exclusivos de PostgreSQL pulados, 180 descobertos. | `resume-fullsqlite.log` |
| Migração da candidata e de uma origem no esquema 0002 da V0.1.3 | Dois ensaios independentes com quatro usuários e dois espaços cada. Hashes de senha, login, sequências, papéis, 15 operações, 19 eventos financeiros de auditoria, saldos e projeções de 60 meses conciliados. A tabela nova de administração técnica recebeu zero eventos na origem antiga. Reenvio da importação reconhecido e falha injetada revertida. | `postgres-migration-evidence.json`, `postgres-legacy-migration-evidence.json` |
| Concorrência e backup | Duas sessões confirmaram a mesma obrigação. Uma recebeu 200, a outra 409. Repetir a operação vencedora preservou um único pagamento. Dois ciclos de dump cifrado e recuperação passaram, com tabelas e sequências iguais. Arquivo danificado, chave incorreta, destino ocupado e sobrescrita foram recusados. | Mesmas duas evidências de migração |
| Reinício e nova instalação | Dois processos HTTP e pastas de aplicação independentes, dois builds de estáticos e duas inicializações do esquema sobre o mesmo PostgreSQL de teste. Compra de R$ 150 em três parcelas e pagamento integral de R$ 50. Após subir a segunda instalação, caixa de R$ 950, dívida de R$ 100, sessão, histórico e projeção idênticos. | `postgres-web-redeploy-evidence.json` |
| Build e partida | **5 grupos aprovados**. Blueprint Free, coleta e resposta dos estáticos, saúde, modo de consulta, proxy HTTPS simulado e recusa pelo script de partida antes de alterar o esquema. Dependências da candidata disponíveis também como wheels para Linux x86-64/CPython 3.14, inclusive Gunicorn e Psycopg. | `deployment-preparation-evidence.json`, `linux-wheelhouse/` |
| Ferramentas e navegador | **12 testes** das ferramentas de gestão, **33 verificações** de valores, sintaxe JS, `pip check` e consistência das migrações aprovados. Chromium passou nos **5 grupos de acesso** e no fluxo geral em 1440×1000 e 390×844, sem erros JS. | `resume-management.log`, `pilot-access-ui-evidence.json`, `ui-evidence.json` |
| Modelo de backup externo | YAML lido, 5 passos de shell analisados e 3 blocos Python compilados. O arquivo permanece fora de `.github/workflows/`. | `backup-template-syntax.json` |

**Preservação da base de uso.** O backup anterior `backups/finance-before-postgres-20261029-163735-5b661d.sqlite3` foi mantido. Antes das alterações desta retomada, foi feita nova cópia consistente em `backups/retomada-20261109-ff066bc.sqlite3`. Sua restauração em arquivo separado passou na integridade e na comparação integral do conteúdo lógico. A assinatura SHA-256 da origem em C: permaneceu igual à registrada em 29/10. Os ensaios PostgreSQL receberam exclusivamente registros fictícios.

## Complemento de 10/11 — senhas das roles no Neon

Hugo forneceu capturas confirmando as duas roles e os privilégios iniciais mínimos, além de uma conexão administrativa TLS 1.3 ao banco `neondb`, servidor PostgreSQL 18.6. O comando `psql \password organiza_app` foi rejeitado pelo Neon com HTTP 400 por fornecer hash pré-calculado. A orientação anterior foi corrigida no guia de roles; naquele momento ainda faltava concluir as senhas e os logins das duas identidades.

Adicionados `tools/set_neon_role_passwords.py` e `tools/test_neon_role_passwords.py`. O utilitário é executado pelo operador, pede senhas ocultas e distintas, verifica o destino e os privilégios, envia somente a alteração de senha por TLS verificado e testa cada login em nova conexão. Não grava segredos localmente, não expõe erros SQL e não modifica permissões, tabelas ou dados financeiros. O provedor recebe a senha original, como exige sua documentação; não há garantia do cliente sobre registros internos do provedor nem rollback conjunto das duas alterações. Dez testes offline passaram na primeira versão; a execução real foi concluída posteriormente, conforme registro abaixo.

Após uma nova captura mostrar erro genérico antes do envio de senha, foi acrescentado o diagnóstico `--check-admin`, somente leitura e com apenas um prompt de senha administrativa. A saída informa etapa e categoria segura de erro, sem mensagens brutas do servidor. **15 testes offline passaram** e stdin redirecionado foi recusado em execução real. O agente confirmou apenas handshake TLS 1.3 com certificado/hostname válidos no endpoint direto, sem autenticação, SQL ou alteração. Essa sondagem isolada não validou os logins; a confirmação autenticada foi realizada pelo operador na sequência.

**Conclusão posterior por Hugo:** o diagnóstico autenticado indicou senha administrativa recusada. Após usar a senha atual, a execução retornou `DIAGNOSTICO_OK`. Hugo concluiu então o modo normal e forneceu captura da confirmação de alteração das duas senhas e verificação de ambos os logins diretos (`codex-clipboard-09bc6a8b-4237-4872-bc15-14a9ae6e12ed.png`). A etapa de senhas e login direto está concluída pelo operador. Credenciais não foram recebidas pelo agente; não houve alteração de tabelas, concessões ou dados financeiros pela ferramenta. Não repetir a configuração de senhas agora. Conexão pooled, permissões após migração e aplicação no Render ainda aguardam validação.

Próxima ação: guardar `DATABASE_URL` pooled de `organiza_app` e `DATABASE_URL_UNPOOLED` direta de `organiza_migrator` no cofre, identificar o Git privado exclusivo e o workspace Render e preparar a aprovação final dos destinos. O PostgreSQL 18.6 exibido no destino exige alinhar as ferramentas de backup/restauração e repetir a validação nessa versão antes do corte. As evidências anteriores em PostgreSQL 17.11 continuam válidas somente para aquele ambiente. Nenhuma migração, publicação ou alteração remota foi executada pelo agente nesta correção.

## Arquivos da preparação

| Área | Arquivos |
| --- | --- |
| Empacotamento e início | `render.yaml`, `build.sh`, `start-render.sh`, `gunicorn.conf.py`, `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitattributes`, `.gitignore` |
| Django e acesso | `config/settings.py`, `config/database.py`, `config/urls.py`, `config/log_filters.py`, `finance/access.py`, `finance/security.py`, `finance/views.py`, `finance/models.py`, `static/app.js`, `static/app.css`, `templates/index.html` |
| Esquema e operação | `finance/migrations/0002_database_guards.py`, `0003_postgres_guards.py` e `0004_pilot_access.py` na mesma pasta, `tools/organiza_runtime.py`, `tools/migrate_schema.py`, `tools/migrate_sqlite_postgres.py`, `tools/postgres_common.py`, `tools/postgres_backup.py` |
| Testes e evidências | `finance/test_hosted_config.py`, `finance/test_postgres_security.py`, `finance/test_pilot_access.py`, `tools/test_postgres_tools.py`, `tools/verify_postgres_migration.py`, `tools/verify_deployment_preparation.py`, `tools/verify_postgres_web.py`. Evidências e bancos de ensaio ficam em `test-results/`, ignorada pelo Git. |
| Operação e documentação | `deploy/postgres-backup.workflow.yml`, `deploy/backup-runner-notes.md`, `docs/HOSTING-NEON-RENDER.md`, `docs/CURRENT-STATE.md`, `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, este relatório e `README.md` |

O Git local está na branch `main`, sem commit, arquivos preparados no índice ou remoto. A tabela identifica os arquivos da entrega por função. O repositório ainda não tem um commit-base para um diff histórico completo. A preparação dispensa reiniciar ou migrar o banco oficial em C:. O esquema novo se aplica ao PostgreSQL dedicado no corte aprovado. Caso a candidata venha a ser adotada como atualização do próprio SQLite local, a migração de administração técnica também será necessária para essa finalidade.

## Pendências externas e próxima decisão

1. **Git privado.** Informar o proprietário e a URL exata de um repositório privado exclusivo do Organiza. Se ele ainda precisar ser criado, propor `<proprietário>/organiza` e a visibilidade Private para aprovação antes de criar. O primeiro envio ocorrerá após conferir o destino e revisar os arquivos incluídos.
2. **Render.** Informar o nome exato do workspace e seu titular. No painel, conferir **Billing → Hobby**, saldo de horas, banda, builds e condição de cobrança zero. O serviço proposto é `organiza-piloto`, uma instância **Free**. O domínio público será conhecido na criação aprovada. As duas pessoas do piloto entram pelo Django.
3. **Neon.** Conferir após autenticação os identificadores fornecidos por Hugo — organização `org-bitter-unit-69231305`, projeto `cool-flower-27024914`, branch `production` — e confirmar banco dedicado, role, região, versão, plano e conteúdo antes de qualquer escrita. O prompt de integração anunciado poderá ser conferido com a configuração Django existente.
4. **Corte e retorno.** Com o conjunto aprovado, congelar a origem, tirar e restaurar a cópia final, aplicar o esquema no destino em manutenção, importar antes de criar administrador e reconciliar. Liberar apenas um banco para escrita. Se houver novas movimentações no PostgreSQL, preservá-las em dump cifrado e recuperar o estado mais recente antes de qualquer retorno. [Roteiro de operação e retorno](HOSTING-NEON-RENDER.md)
5. **Homologação externa.** Faltam TLS e pool reais do Neon, build e execução Linux/Gunicorn no Render, HTTPS público, despertar após inatividade, reinício/redeploy hospedados e acesso físico com o computador-base desligado. O backup externo ainda depende da conta `imd.hugo@dasemper.com`, da pasta autorizada, do executor e do ensaio de recuperação pelo Drive. [Procedimento de backup](../deploy/backup-runner-notes.md)

A gratuidade depende da conta e das cotas disponíveis. O Render oferece 750 horas mensais compartilhadas e pode suspender após 15 minutos ocioso. O Neon anuncia 1 GB de banco e 100 CU-horas mensais por projeto no Free. As contas e condições efetivas precisam ser confirmadas antes da aprovação. [Render Free](https://render.com/docs/free) · [Neon Free](https://neon.com/pricing)

**Próxima ação de Hugo:** informar os dois destinos, existentes ou propostos, e conferir por leitura o projeto Neon indicado. A partir disso, apresentar o conjunto exato para aprovação de criação, primeiro envio, publicação e importação real. Nenhuma dessas operações foi executada nesta preparação.
