# Organiza — roles do banco e segredos do Render

**Procedimento vigente em 11/11/2026:** consulte [PILOT-RENDER-CONFIG.md](PILOT-RENDER-CONFIG.md). O serviço web recebe somente `DATABASE_URL` de `organiza_app`. A conexão `DATABASE_URL_UNPOOLED` de `organiza_migrator` fica no cofre e em processo de manutenção separado, nunca no Web Service ou nos seus Environment Groups. As evidências assistidas de 10/11 abaixo permanecem válidas; não recriar roles nem redefinir senhas.

Conferência de 10/11/2026. Hugo informou no painel Neon o projeto `cool-flower-27024914`, a região São Paulo, a branch `production` e o banco `neondb`. A organização informada anteriormente é `org-bitter-unit-69231305`. Capturas posteriores de consultas executadas por Hugo confirmaram as duas roles e os privilégios iniciais descritos abaixo. O psql de Hugo conectou por TLS 1.3 como `neondb_owner` e mostrou servidor PostgreSQL **18.6**. São evidências fornecidas pelo operador; o agente não autenticou no provedor. Plano, objetos e preparação completa ainda exigem conferência na janela autorizada.

## Identidades para a candidata

| Uso | Login no PostgreSQL | Conexão e alcance |
| --- | --- | --- |
| Django e requisições HTTP | `organiza_app` | Pooled, mesmo banco e branch. Lê e altera as tabelas necessárias para autenticação, sessões, espaços e finanças. Operações e auditoria recebem leitura e inserção. Sem propriedade dos objetos, criação de tabelas, alteração de gatilhos ou modo de importação. |
| Migrações Django e importação autorizada | `organiza_migrator` | Direta, pooling desligado. Pode criar no schema `public` do banco dedicado. É proprietária das tabelas, sequências e funções que cria. O importador pode preservar a autoria histórica e ajustar sequências. A role não precisa ser proprietária do banco nem membro de `neon_superuser`. |
| Preparação administrativa inicial | `neondb_owner` | Operador verifica o destino e concede os privilégios iniciais. A credencial permanece no ambiente administrativo. |

Os dois primeiros logins foram testados com identidades equivalentes em PostgreSQL local. As capturas do Neon confirmaram LOGIN habilitado, ausência dos atributos administrativos consultados e de associações a outras roles, CONNECT/USAGE para ambas, CREATE em `public` apenas para `organiza_migrator`, e ausência de CREATE/TEMP no banco para ambas. Hugo concluiu a definição das duas senhas e confirmou ambos os logins diretos com TLS pelo utilitário, conforme relato e captura da mensagem final. A conexão pooled ainda não foi testada. Administrador, colaborador e leitor continuam sendo papéis de **participantes do espaço no Django**. A aplicação informa o ator dentro de cada transação. Esse mecanismo pressupõe que a credencial web seja mantida em segredo, pois ela permite operações do serviço em vários espaços.

## Antes de qualquer criação ou alteração externa

No Neon, selecione o projeto, a branch e o banco informados. Confira as roles existentes e o proprietário do banco, a disponibilidade de `public`, as tabelas, seus proprietários, privilégios de PUBLIC e eventuais consumidores do banco. Se houver objetos de outro serviço ou materiais do Organiza já importados, interrompa o provisionamento e identifique o histórico. Se alguma role já existir, confira suas associações e privilégios efetivos. O bootstrap abaixo não deve ser repetido para as roles já confirmadas. A definição autorizada de senhas é uma etapa separada e preserva as propriedades e concessões existentes.

Após a aprovação do destino dedicado e vazio, um administrador pode preparar os logins por **SQL**. A criação padrão de uma role pelo Console Neon pode conceder `neon_superuser`. O exemplo abaixo é para o caso em que **ambas as roles estão ausentes**. As revogações de PUBLIC afetam outras conexões do banco e precisam fazer parte da aprovação. [Privilégios das roles Neon](https://neon.com/docs/manage/roles) · [Privilégios PostgreSQL](https://www.postgresql.org/docs/current/ddl-priv.html)

```sql
BEGIN;
CREATE ROLE organiza_app LOGIN;
CREATE ROLE organiza_migrator LOGIN;
REVOKE CREATE, TEMPORARY ON DATABASE neondb FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE neondb TO organiza_app, organiza_migrator;
GRANT USAGE ON SCHEMA public TO organiza_app, organiza_migrator;
GRANT CREATE ON SCHEMA public TO organiza_migrator;
COMMIT;
```

**Correção do procedimento de senhas, 10/11:** não usar `psql \password` neste destino Neon. A captura de Hugo mostrou HTTP 400 com `Neon only supports being given plaintext passwords`. O comando do psql transforma a senha no cliente; o Neon exige o valor original em `ALTER ROLE ... PASSWORD`, transportado por TLS, e não aceita hashes fornecidos pelo cliente. Naquela tentativa de `organiza_app`, nenhuma definição de senha foi confirmada; o fluxo corrigido foi concluído depois, conforme registro abaixo. [Regra do Neon](https://neon.com/docs/manage/roles#manage-roles-with-sql) · [Comando psql](https://www.postgresql.org/docs/17/app-psql.html)

Para concluir a etapa autorizada, sair do psql com `\q` e executar `tools/set_neon_role_passwords.py` com o Python da `.venv`, em PowerShell interativo. O utilitário fixa o host direto informado por Hugo e o banco `neondb`, pede a senha administrativa e as duas novas senhas com entrada oculta, exige senhas distintas com pelo menos 24 caracteres ASCII sem espaços, revalida identidade e privilégios antes da alteração e envia somente `ALTER ROLE ... PASSWORD` para as duas roles permitidas. Usa `sql.Identifier`/`sql.Literal`, TLS `verify-full` com certificado e `channel_binding=require`. Depois de cada alteração, abre nova conexão para verificar o login da role. Não cria roles ou tabelas, não altera concessões, não inicia o Django, não lê `.env` e não importa dados.

Gere e guarde senhas aleatórias distintas no gerenciador de senhas. O utilitário não grava senhas em arquivos, argumentos, histórico do terminal ou mensagens de erro. Ele não promete ausência de retenção no servidor: o Neon recebe o literal de senha e o registro interno do provedor está fora do controle do cliente. A operação ocorre por role; se a segunda falhar, uma primeira alteração confirmada pode permanecer aplicada. Erros do driver são omitidos para não revelar SQL ou credenciais. Não enviar senhas pelo chat ou SQL Editor.

Validação local inicial desta correção: dez testes offline cobriram entrada oculta sem fallback, confirmação, senhas distintas, recusa de entradas inválidas, TLS, identidade/permissões, escape SQL, recusa de outra role, supressão de erro com segredo e verificação separada de login. A execução real foi posteriormente concluída por Hugo, conforme registro abaixo.

**Diagnóstico posterior, 10/11:** Hugo mostrou uma recusa local por reutilização de senha e, em nova execução, um erro genérico antes de qualquer mensagem de envio de alteração. Foi acrescentado `--check-admin`, que solicita somente a senha atual de `neondb_owner`, conecta e executa as consultas de identidade/permissões, sem `ALTER ROLE` ou novas senhas. Mensagens por etapa e códigos fixos distinguem recusa de autenticação, certificado, channel binding, DNS, timeout e permissão; SQLSTATE válido pode ser mostrado, mas SQL, mensagens brutas e segredos continuam omitidos. O modo de alteração também distingue uma falha anterior ao envio de uma alteração possivelmente aplicada após envio.

Agora **15 testes offline passaram**, incluindo o modo somente leitura, classificação sanitizada e falha após envio. A execução real com entrada redirecionada foi recusada antes da conexão. Uma sondagem do agente ao endpoint direto confirmou handshake TLS 1.3, cadeia do certificado e hostname válidos com o mesmo bundle CA, sem autenticação, senha ou SQL. Essa sondagem isolada não comprova autenticação pelo driver. Psycopg local 3.3.6, libpq 18.4. Nenhuma alteração remota foi executada pelo agente.

**Conclusão assistida, 10/11:** o diagnóstico executado por Hugo informou `AUTENTICACAO_RECUSADA` para `neondb_owner`. Depois de usar a senha administrativa atual, Hugo apresentou `DIAGNOSTICO_OK`, confirmando login, banco e privilégios pelo driver. Em seguida, o modo normal retornou `Concluido: as duas senhas foram alteradas e os dois logins diretos foram verificados`, confirmado por Hugo e pela captura final `codex-clipboard-09bc6a8b-4237-4872-bc15-14a9ae6e12ed.png`. A etapa de senhas está concluída. São resultados fornecidos pelo operador, sem envio de credenciais ao agente. A ferramenta não alterou tabelas, concessões ou dados financeiros. O modo normal redefine as senhas; não precisa ser repetido agora.

Próxima ação: guardar as duas URIs no cofre conforme a seção seguinte, conferir Git privado e workspace Render, validar pooling e preparar a aprovação final. A etapa de login direto não comprova permissões sobre tabelas ainda não migradas nem operação do aplicativo hospedado.

O dono original do banco continua o mesmo. Na migração inicial do Organiza, execute todo o esquema como `organiza_migrator`, inclusive a migração `0005_import_owner`. Em caso de esquema já existente com outro proprietário, avaliar o ajuste separadamente antes de executar o corte. O servidor remoto mostrado é PostgreSQL 18.6, enquanto os ensaios anteriores usaram 17.11. Antes do corte, preparar ferramentas de backup/restauração da versão 18 e repetir a validação compatível; `pg_dump` 17 não exporta um servidor 18. [Compatibilidade do pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html#APP-PGDUMP-NOTES)

**Separação reforçada em 11/11:** o build e o iniciador do Render não aplicam esquema e não recebem a credencial de migração. `start-render.sh` remove variáveis de manutenção herdadas, verifica o Django, confere a role web e os privilégios em transação somente leitura por `tools/check_runtime_database.py` e inicia Gunicorn. O esquema deve estar previamente migrado, incluindo `0005_import_owner`; tabelas ausentes, privilégios incompatíveis ou importação liberada à role web impedem a subida. Não se concede leitura de `django_migrations` à aplicação.

`python tools/migrate_schema.py --render-roles` fica reservado a uma sessão de manutenção aprovada, fora do Web Service e de seus Environment Groups, usando o mesmo commit a publicar. Somente esse processo recebe ambas as URIs para conferir os endpoints, migrar sob bloqueio pela conexão direta e conceder os acessos de `tools/render_roles.py`. Tabelas futuras exigem revisão explícita. Encerrar a sessão ao concluir. O Render Free não oferece pre-deploy command, Shell ou one-off job; a manutenção ocorre pelo operador ou executor isolado aprovado. [Deploys](https://render.com/docs/deploys) · [Free](https://render.com/docs/free)

## Cadastrar as conexões em ambiente seguro

1. Depois de confirmar as roles e a autorização, abra **Neon → Connect**. Fixe `production` e `neondb`. Selecione **organiza_app**, ligue **Connection pooling** e copie a URI PostgreSQL para o campo seguro destinado a `DATABASE_URL`. O nome do host inclui `-pooler`. Copie a URI sem o comando `psql`, sem aspas e mantendo as opções de SSL.
2. Na mesma janela, mantenha a branch e o banco, selecione **organiza_migrator** e desligue **Connection pooling**. Guarde a URI direta no cofre como `DATABASE_URL_UNPOOLED`, exclusiva do processo de manutenção. O endpoint deve corresponder ao mesmo compute. Se a interface mostrar um marcador em lugar da senha da role SQL, complete o valor apenas no gerenciador seguro, com a senha dessa role codificada para URI. O cliente do projeto exige TLS com validação de certificado e nome do servidor. [Conexões Neon](https://neon.com/docs/connect/connection-pooling)
3. No serviço **aprovado** do Render, abra **Environment → Environment Variables → Add Environment Variable**. Cadastre somente os dois segredos da tabela abaixo no serviço exclusivo do Organiza. Não adicione `DATABASE_URL_UNPOOLED`, `APP_USE_DIRECT_DATABASE` nem credenciais administrativas, inclusive em Environment Groups vinculados. Em serviço existente, use **Save only** sem iniciar deploy. Se ainda não existir, conserve os valores no cofre até a criação autorizada. Aplicar um Blueprint novo inicia a implantação. [Segredos no Render](https://render.com/docs/configure-environment-variables)
4. Preserve a instalação de C: e seu `.env` local. Para migração manual na janela autorizada, forneça as variáveis no processo do operador por um cofre e use a conexão direta da role de migração. Os segredos de um futuro executor de backups têm escopo próprio e exigem aprovação separada.

| Nome exato no Render | Origem ou valor inicial |
| --- | --- |
| `DATABASE_URL` | Segredo, URI pooled de `organiza_app` |
| `APP_SECRET_KEY` | Segredo Django distinto das duas senhas, aleatório e estável, pelo menos 50 caracteres |
| `APP_ENVIRONMENT` | `production` |
| `APP_LOCAL_MODE` | `false` |
| `APP_DEBUG` | `false` |
| `APP_REGISTRATION_MODE` | `approval` |
| `APP_READ_ONLY` | `true` até a reconciliação e a liberação aprovadas |
| `PYTHON_VERSION` | `3.14.6` |

O Blueprint já define os seis valores comuns. O Render fornece `PORT` e `RENDER_EXTERNAL_HOSTNAME`. Domínio personalizado aprovado exige também `APP_ALLOWED_HOSTS` e `APP_CSRF_TRUSTED_ORIGINS` exatos. São Paulo é a região do banco. Hugo escolheu **My Workspace / Free / Virginia (US East)** para o web; `region: virginia` já consta no manifesto. Titular, seleção e cotas ainda precisam ser conferidos no painel. [Regiões do Render](https://render.com/docs/regions)

## Git, evidências e pendências

**Situação posterior confirmada em 11/11:** o repositório agora é privado. Hugo autorizou sincronizar a candidata com `main`, sem deploy; o registro vigente está em [SYNC-MAIN-2026-11-11.md](SYNC-MAIN-2026-11-11.md). A comparação abaixo é histórica e não deve motivar nova solicitação de URL ou de mudança de visibilidade.

A conta autenticada no conector GitHub é `HugoMota-IMD`. O repositório identificado pelo README do Organiza é **público**. A `main` consultada em 10/11 aponta para `9b0b470fb2f38b127408fcd0913a93bc3684f0b1`. A comparação pelo conteúdo contra a candidata de 09/11, antes dos ajustes desta rodada, encontrou **56 arquivos em comum idênticos e 14 em comum diferentes**. O manifesto Render coincide. O início do serviço, a configuração PostgreSQL e as ferramentas de migração diferem. O relatório da candidata e o ensaio HTTP entre duas instalações estavam ausentes no remoto. O checkout em C: segue sem commit ou remoto configurado. A candidata integral e os ajustes de roles desta rodada ainda estão locais. [Commit consultado](https://github.com/HugoMota-IMD/SISTEMA-DE-ORGANIZA-O/commit/9b0b470fb2f38b127408fcd0913a93bc3684f0b1)

O braço web do ensaio usou uma role sem propriedade e executou cadastro pendente, aprovação, inclusão em espaço, login, pagamento e troca de instalação preservando sessão e saldo. Houve negativas reais de DDL, truncamento, alteração de histórico, elevação à role de migração e atualização do sinalizador de superusuário. A role web não conseguiu ativar o modo de importação. A role dedicada de migração criou o esquema e importou as fixtures atual e legada, com reconciliação e restauração cifrada aprovadas. A suíte completa passou nos 180 testes PostgreSQL e em 170 testes SQLite, com 10 exclusivos de PostgreSQL pulados. Passaram ainda os 13 testes das ferramentas e as 5 verificações do pacote Render. Evidências em `test-results/postgres-web-redeploy-evidence.json`, `postgres-migration-evidence.json`, `postgres-legacy-migration-evidence.json` e `roles-*.log`.

**Próxima ação atualizada em 11/11:** conferir a visibilidade Private do repositório já informado e a seleção/titular/cotas de My Workspace / Free / Virginia. As duas URIs ficam no cofre, mas somente a pooled pertence ao web. As roles e logins diretos permanecem confirmados pelo operador. PostgreSQL 18.6 e PgBouncer local passaram nos ensaios da retomada; pool Neon, conteúdo do destino, permissões sobre tabelas após migração e execução no Render ainda aguardam a janela aprovada. Não repetir a configuração de senhas. Estado atual, relatório e campos exatos em [PILOT-RENDER-CONFIG.md](PILOT-RENDER-CONFIG.md).
