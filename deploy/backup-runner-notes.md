# Backup externo — template inativo e aprovação pendente

O arquivo `deploy/postgres-backup.workflow.yml` é apenas um **template fora de `.github/workflows`**. Não foi enviado ao GitHub, executado, agendado ou conectado ao Drive/Neon. O cron diário 07:00 UTC (**03:00 America/Manaus**) está comentado. Nenhuma credencial ou chave privada está no código. Esta preparação não configura a automação externa exigida para operação: essa pendência continua aberta.

## Arquitetura e custo

Depois de aprovado, um runner GitHub-hosted **Ubuntu 24.04 padrão** poderá executar o backup independentemente do Render e do computador base. Não usar Render Cron pago, runner maior ou runner no computador que pode ser desligado. O processo web não agenda o backup e pode estar suspenso.

O planejamento inicial considera a referência tradicional GitHub Free de **2.000 minutos/mês e 500 MB de armazenamento**, compartilhados pelo titular entre repositórios. A documentação de cobrança atual também apresenta alocações de compute em valor monetário; portanto esses números **não constituem garantia para a conta concreta**. Antes de habilitar, conferir Billing/Usage do titular, cota restante, política de bloqueio ao esgotar e orçamento **zero com interrupção de uso**, sem autorizar excedentes. Ausência de cobrança adicional não significa execução garantida: quota esgotada ou bloqueio pode impedir o backup. Não aceitar upgrade, conversão automática ou cartão para liberar uso cobrado. Fontes: [preços GitHub](https://github.com/pricing), [cobrança Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

O template não cria artifacts ou caches do Actions. Só envia ao Drive os dois arquivos explicitamente selecionados: dump `.age` cifrado e manifesto `.age.json` com checksum/tamanho/data, sem valores financeiros. O Drive também precisa de espaço suficiente dentro da franquia existente; nenhuma ampliação foi contratada.

## Itens indispensáveis antes de ativar

1. Aprovar repositório privado exato, titular/workspace, banco/branch Neon de produção e conexão direta. Não usar outro projeto nem o endpoint `-pooler`.
2. Confirmar a conta **imd.hugo@dasemper.com** e o **ID exato da pasta oficial de backups**. A pasta precisa estar acessível ao aplicativo OAuth aprovado; nenhum ID foi inventado ou criado nesta tarefa. Confirmar também quem pode acessar essa pasta; o dump continua cifrado mesmo dentro dela.
3. Aprovar/reutilizar um aplicativo OAuth próprio para o uploader do Drive. O rclone informa que seu `client_id` compartilhado está em aposentadoria em 2026. O template recusa configuração sem client ID/secret próprios; não cria aplicativo ou projeto Google automaticamente. Isso é autorização de API de backup, não hospedagem Google Cloud. Se exigir nova configuração externa, ela integra a aprovação final; não prosseguir silenciosamente. [rclone Drive](https://rclone.org/drive/).
4. Preparar um remote rclone dedicado chamado `organiza_backup`, do tipo Drive, para essa identidade. Fazer login/consentimento pelo fluxo apropriado, sem enviar tokens ou strings de conexão pelo chat. Usar escopo mínimo que ainda permita a pasta aprovada: `drive.file` só enxerga arquivos/pastas criados ou autorizados pelo próprio app; não ampliar escopos automaticamente para contornar uma negativa.
5. Gerar a chave age definitiva em ambiente seguro. Guardar o recipient **público** no runner e a identidade **privada somente fora do Git e fora do CI**, em cofre protegido com recuperação sob responsabilidade definida. Nunca reutilizar a identidade fictícia do ensaio local. Sem a chave privada, o backup cifrado não pode ser recuperado.
6. Conferir a versão principal no servidor Neon e informar seu número em `NEON_SERVER_MAJOR`. O executor instala o cliente PostgreSQL dessa versão e verifica a versão do servidor antes da cópia. O ensaio local passou com cliente e servidor **17.11**. Se a versão aprovada for outra, repetir o ciclo de recuperação nessa versão.
7. Repetir restauração de um arquivo obtido do destino externo em **outro banco vazio**, usando a versão aprovada, e conferir todos os registros/sequências, hashes de senha/login, permissões, saldos e projeções. O roundtrip age/PG local já passou, mas isso não comprova OAuth, upload ou recuperação do Drive.

## Variáveis, segredos e barreiras

O job só aceita execução quando as três variáveis de repositório estão exatamente `true`:

- `ORGANIZA_BACKUPS_APPROVED`: aprovação do conjunto e do ambiente de produção.
- `BACKUP_DRIVE_CONFIRMED`: confirmação humana de conta, pasta, escopo e uploader.
- `BACKUP_FREE_QUOTA_CONFIRMED`: franquia/cobrança/blocking conferidos para a conta real.

Demais variáveis de repositório: `AGE_RECIPIENT` (pública), `DRIVE_ACCOUNT_EMAIL=imd.hugo@dasemper.com`, `DRIVE_BACKUP_FOLDER_ID`, `NEON_DIRECT_HOST`, `NEON_DATABASE_NAME` e `NEON_SERVER_MAJOR`. Os valores exatos do destino ainda dependem da escolha/aprovação; não há placeholder que habilite o job por acidente.

Somente dois segredos de repositório são esperados: `DATABASE_URL_UNPOOLED` e `RCLONE_CONFIG`. O segundo contém a configuração OAuth dedicada e seu refresh token; o runner grava uma cópia em arquivo temporário com modo **0600** e remove somente esse arquivo ao terminar. Não definir `AGE_IDENTITY_FILE` ou chave age privada no CI. Não exibir segredos, passfiles, perfil do usuário, resposta OAuth ou conteúdo de dump nos logs.

Antes de transferir qualquer arquivo, o template:

- Confere host/banco aprovados, conexão direta TLS e major PostgreSQL.
- Renova OAuth sem imprimir credenciais e lê `about.user.emailAddress` para comparar à conta aprovada.
- Lê somente a pasta indicada e confirma ID, tipo, situação e permissão de adicionar arquivos.
- Cifra o dump local antes do upload, verifica seu manifesto e copia somente `.age` + `.age.json`, com opção imutável.
- Confere o transporte dos arquivos cifrados. Não executa `sync`, purge, delete, compartilhamento público ou limpeza remota.

Os passos Google OAuth e Drive existem apenas no template inativo; **nenhuma dessas chamadas foi executada nesta preparação**. As APIs são as oficiais [OAuth para aplicação web](https://developers.google.com/identity/protocols/oauth2/web-server#offline), [Drive about.get](https://developers.google.com/drive/api/reference/rest/v3/about/get) e [files.get](https://developers.google.com/drive/api/reference/rest/v3/files/get).

## Frequência, retenção e alerta

Proposta a aprovar: um backup diário às 03:00 Manaus; conservar **14 diários, 8 semanais e 6 mensais**. Antes de aceitar essa retenção, medir o tamanho de um dump cifrado, projetar o conjunto (até 28 cópias se houver sobreposição) e conferir a capacidade do Drive, as cotas Neon e as cotas Actions compartilhadas. O template atual cria apenas a cópia diária; classificação semanal/mensal e política remota de retenção **não foram ativadas**.

Também estimar a saída de dados do Neon em cada dump completo, somada ao tráfego normal da aplicação. Compactar/cifrar no runner não elimina o tráfego já recebido do banco. Se a frequência diária não couber nas franquias gratuitas, revisar o conjunto antes de ativar, sem contratar excedentes automaticamente.

Não há exclusão automática de backups neste template. O responsável deve revisar e autorizar a remoção de cópias conforme a política aprovada, preservando pontos de recuperação necessários. Não usar exclusão por idade sem conferir integridade, retenção e recuperação antes. Enquanto a política não for implementada, o uso de armazenamento crescerá e precisa ser acompanhado.

Definir responsável e canal de alerta de falha usando o mecanismo aprovado do executor; nenhum e-mail/mensagem foi configurado ou enviado aqui. Backups interrompidos por quota, suspensão do executor, falha OAuth ou falta de espaço devem ser tratados como falha, não como backup concluído. O GitHub não garante disparo do cron no segundo exato; isso não é um SLA de produção.

## Recuperação

Baixar somente os arquivos cifrados e seu manifesto da pasta aprovada, verificar checksum e usar uma máquina segura com a identidade age privada. Preparar **outro PostgreSQL vazio**, com conexão direta e clientes compatíveis. Nunca restaurar por cima do banco em uso.

```powershell
# Variáveis secretas fornecidas por mecanismo seguro; não escrever valores no chat.
.\.venv\Scripts\python.exe tools\postgres_backup.py restore --source backups\arquivo.dump.age --confirm-empty-target --approved-real-restore
```

Esse sinalizador real só deve ser usado depois da aprovação do incidente/destino. O procedimento local de ensaio usa bancos `organiza_test_*` separados e não precisa autorizar um destino real. A restauração é transacional e recusa banco ocupado, arquivo corrompido ou chave errada. Depois, executar reconciliação e login e só então aprovar eventual troca do destino oficial. Se houve gravações após uma migração, recuperar o estado PostgreSQL atual em vez de simplesmente reativar o SQLite antigo.

## Dependências verificadas e teste realizado

O cliente PostgreSQL vem do repositório APT oficial, com chave específica e validação de assinaturas. Os pacotes age e rclone vêm dos repositórios assinados da distribuição. [PostgreSQL no Ubuntu](https://www.postgresql.org/download/linux/ubuntu/)

Actions fixadas por SHA consultada na API oficial em 29/10/2026: checkout **v7.0.1** (`3d3c42e5aac5ba805825da76410c181273ba90b1`) e setup-python **v7.1.0** (`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`). O template precisa de revisão de dependências antes de qualquer habilitação futura.

Nesta preparação, foi validada somente a sintaxe YAML e a compilação dos blocos Python embutidos, sem executá-los. O executor GitHub, o OAuth, o upload Drive, o cron e a restauração externa **não foram testados nem configurados**. A evidência já existente `test-results/postgres-migration-evidence.json` comprova o dump cifrado/recuperação **locais e fictícios**, incluindo comparação integral de tabelas/sequências, chave errada, corrupção e recusa de sobrescrita.
