# Organiza — configuração do piloto para aprovação — 11/11/2026

Candidata **0.2.0-prep**. Hugo confirmou a mudança do repositório para privado e autorizou sincronizar a versão testada com `main`, sem deploy. Essa autorização não inclui criação/publicação de serviço, migração do Neon ou importação real. Instalação, SQLite original e backups em C: preservados. Nenhuma role ou senha Neon foi alterada pelo agente.

## Repositório e commit

Consulta autenticada após a confirmação de Hugo: `HugoMota-IMD/SISTEMA-DE-ORGANIZA-O`, proprietário e conta autenticada HugoMota-IMD, **visibilidade private** e permissão de escrita. README e árvore indicam somente o Organiza. Essa verificação de conteúdo não é uma auditoria de todos os commits históricos. A exigência de repositório privado está atendida.

`main`: **9b0b470fb2f38b127408fcd0913a93bc3684f0b1**, de 03/11/2026. Comparação por hashes Git dos arquivos, normalizando CRLF/LF: 53 arquivos comuns iguais, 17 diferentes. Estão ausentes no remoto, entre outros, `finance/migrations/0005_import_owner.py`, `tools/render_roles.py`, `tools/check_runtime_database.py`, o ensaio de duas instalações web e a documentação vigente. O remoto tem `.github/workflows/verificar.yml` e `IMPORTACAO.md` sem correspondentes locais; preservá-los e reconciliá-los no envio autorizado. Evidência: `test-results/pilot-main-comparison-20261111.json`.

**Não usar o commit-base acima para o piloto preparado.** Esta revisão incorpora a candidata testada sobre esse histórico, conservando o workflow remoto e excluindo dados/segredos. O SHA resultante será conferido em `main` e registrado no recibo local e na entrega do chat; ver [SYNC-MAIN-2026-11-11.md](SYNC-MAIN-2026-11-11.md). A sincronização usa o conector autenticado: o Git do Windows não dispõe de login para acessar o privado. A pasta operacional e seu histórico Git local ainda sem primeiro commit não são reinicializados nem sobrescritos. Somente o novo commit poderá ser apresentado para aprovação de implantação.

## Campos exatos do Render

Os destinos abaixo foram informados por Hugo; não houve autenticação no painel Render nesta rodada.

| Campo | Valor preparado |
| --- | --- |
| Workspace | `My Workspace` — conferir titular e plano/cotas no painel |
| Repository | `HugoMota-IMD/SISTEMA-DE-ORGANIZA-O`, privado confirmado |
| Branch | `main`, no novo commit aprovado |
| Runtime | `Python 3` |
| Instance Type | `Free`, uma instância |
| Region | `Virginia (US East)`; Blueprint `virginia` |
| Root Directory | **Deixar vazio**: `manage.py`, `build.sh` e `start-render.sh` estão na raiz |
| Build Command | `bash build.sh` |
| Start Command | `bash start-render.sh` |
| Health Check Path | `/api/health` |
| Auto-Deploy | `Off`; Blueprint `autoDeployTrigger: off` |
| Pre-Deploy Command | Não configurar |

As referências executáveis são `render.yaml`, `build.sh`, `start-render.sh`, `gunicorn.conf.py`, `config/settings.py` e `config/database.py`. O build instala versões fixadas, verifica dependências/configuração e coleta estáticos. A partida faz verificação somente leitura de identidade, privilégios e esquema já migrado, depois inicia Gunicorn com um worker e duas threads. Não há SQLite de fallback nem migração automática. `/api/health` confirma o processo, sem consultar o banco; não substitui a homologação financeira.

## Segredos e variáveis

| Variável | Valor/local |
| --- | --- |
| `DATABASE_URL` | **Render web → Environment**: URI pooled da role existente `organiza_app`, banco `neondb`, branch `production` |
| `APP_SECRET_KEY` | **Render web → Environment**: segredo Django aleatório, estável, pelo menos 50 caracteres; diferente das senhas PostgreSQL |
| `PYTHON_VERSION` | `3.14.6` |
| `APP_ENVIRONMENT` | `production` |
| `APP_LOCAL_MODE` | `false` |
| `APP_DEBUG` | `false` |
| `APP_REGISTRATION_MODE` | `approval` |
| `APP_READ_ONLY` | `true` até a liberação aprovada; bloqueia POST, inclusive login, enquanto em manutenção |
| `DATABASE_URL_UNPOOLED` | **Somente cofre/processo isolado de manutenção**: URI direta de `organiza_migrator`; não cadastrar no Render web nem nos grupos de ambiente vinculados |

O Render fornece `PORT` e `RENDER_EXTERNAL_HOSTNAME`; não inventar esses valores. O hostname gera os hosts e a origem HTTPS confiáveis. Domínio personalizado aprovado exige `APP_ALLOWED_HOSTS` e `APP_CSRF_TRUSTED_ORIGINS` específicos. `APP_USE_DIRECT_DATABASE` é seletor interno das ferramentas de manutenção; não configurar no web. Não copiar variáveis locais SQLite/Tailscale. `APP_DATABASE_SSLROOTCERT` não precisa ser configurada para o Neon: o projeto usa o bundle CA do certifi e força `sslmode=verify-full`.

Procedimento seguro: no Neon Connect, manter o destino existente e escolher `organiza_app` com pooling ligado para a URI de aplicação. No cofre, manter separadamente `organiza_migrator` com pooling desligado e o mesmo banco/branch. Não redefinir senhas. Não enviar URIs ou credenciais pelo chat. Em serviço Render já criado, conferir Environment e grupos vinculados e usar **Save only** quando disponível, sem deploy. Na tela de criação, manter a configuração preparada e não pressionar **Deploy Web Service**. Aplicar Blueprint novo também inicia implantação e continua pendente.

`neondb_owner` continua exclusiva do operador administrativo. A aplicação não possui tabelas/schema, não cria objetos e não pode elevar role, alterar histórico ou acionar importação privilegiada. Migrações criam objetos como `organiza_migrator`; as concessões de runtime são explícitas em `tools/render_roles.py`.

## Migração separada e roteiro de publicação

1. Hugo confere privacidade do repositório e My Workspace/Free/Virginia, titular, cotas e eventual cobrança. Registrar o novo SHA após o envio expressamente autorizado, preservando o histórico remoto.
2. Em janela aprovada, usar checkout isolado desse mesmo SHA e ambiente de manutenção que não leia o `.env` local em uso. Carregar segredos pelo cofre em variáveis do **processo**, sem argumentos ou transcrição. Definir `APP_ENVIRONMENT=production`, `APP_LOCAL_MODE=false`, `APP_DEBUG=false`, `APP_REGISTRATION_MODE=approval`, `APP_READ_ONLY=true`, `APP_SECRET_KEY`, hosts HTTPS aprovados e ambas as URLs. Conferir destino/proprietários/conteúdo por leitura; não prosseguir sobre objetos inesperados.
3. Executar **somente após aprovação do esquema remoto**: `python tools/migrate_schema.py --render-roles`. A ferramenta valida as duas identidades, usa bloqueio na conexão direta, aplica migrações e concede os acessos da aplicação. Encerrar a sessão de manutenção e retirar os segredos do processo. Não executar pelo start/build do Render.
4. Se o corte de dados reais for aprovado separadamente: congelar a origem, criar e restaurar backup novo, importar antes de criar usuários no destino e reconciliar. Seguir `HOSTING-NEON-RENDER.md`. Ferramentas `pg_dump`/`pg_restore` devem ser da versão 18 para esse servidor. O laboratório Linux oferece as ferramentas 18 para ensaios; o binário Windows 17 anterior não foi substituído e não deve ser usado para exportar o Neon 18.
5. Conferir no Render que existe apenas a credencial de aplicação, sem migrator ou owner também nos grupos de ambiente. Publicar o **SHA aprovado** manualmente e inicialmente em manutenção. Verificar build, logs sanitizados, saúde e estáticos.
6. Autorizar `APP_READ_ONLY=false` somente após reconciliação. Homologar login, administrador/colaborador/leitor, espaços, pagamento integral/parcial, fatura, reenvio e persistência. Testar celular/outra rede, computador-base desligado, suspensão/retomada e redeploy reais. Atualizar também o manifesto aprovado para preservar a liberação em futuras sincronizações.

O Free não tem pre-deploy command, Shell ou one-off job; por isso a manutenção acontece fora do serviço. Virginia e São Paulo são regiões distintas; latência e despertar ainda precisam de medição no destino. [Render Free](https://render.com/docs/free) · [Deploys](https://render.com/docs/deploys) · [Neon pooling](https://neon.com/docs/connect/connection-pooling)

## Evidências desta rodada

Resultado final aprovado: PostgreSQL/pg_dump **18.6**, PgBouncer **1.26.1**, Python **3.14.6**; **180 testes Django**, **28 testes das ferramentas**, **5 grupos de preparação** e os ensaios de migração/restauração, pool e Gunicorn. Versões em `test-results/pilot18-evidence.json`; logs/JSON em `test-results/pilot18-20261111/`. O laboratório roda serviços reais em Linux, dentro de container sem rede externa, sem portas publicadas e sem montar os dados do host. O contexto contém apenas código; `.dockerignore` usa lista permitida e exclui `.env`, SQLite, backups e segredos. Senhas e certificados são fictícios e gerados dentro dele.

A prova do pool usa `pool_mode=transaction`, uma conexão de servidor, clientes independentes e concorrentes. Verifica o mesmo PID PostgreSQL, encerramento do contexto de ator após commit/rollback/savepoint, negações SQL e acesso HTTP por papel/espaço. A leitura é isolada pelos filtros/autorização do Django; a credencial web é uma identidade de serviço confiável e não fornece RLS independente por usuário final. Não compartilhar essa credencial com participantes.

Neon: a evidência de logins diretos de ambas as roles é a execução assistida de Hugo em 10/11. Nenhuma conexão autenticada, ensaio de escrita ou mudança de roles/senhas foi realizada pelo agente no Neon nesta rodada. Pool, permissões sobre o esquema após migração e aplicação completa **ainda não foram testados no Neon**. Render: configuração preparada, sem deploy, teste de suspensão ou acesso público real. Os resultados locais não substituem esses passos.

Para repetir o ensaio em Docker já disponível, na raiz do projeto: `docker build -f deploy/pilot-lab.Dockerfile -t organiza-pilot-lab .`, depois `docker run --name organiza-pilot-lab-ensaio --network none --add-host lab.local:127.0.0.1 --add-host lab-pooler.local:127.0.0.2 organiza-pilot-lab`. Usar nome novo, sem `--env-file`, volumes ou `-p`. Copiar apenas os JSON de evidência e logs do ensaio; não copiar bases fictícias sobre a instalação. O runner encerra os serviços internos ao terminar.
