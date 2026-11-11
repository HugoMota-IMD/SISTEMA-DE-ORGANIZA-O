# Sistema de Organização Financeira

Área operacional do **Sistema de Organização Financeira** para execução no Codex.

## Integração oficial

- ChatGPT: `COMANDO MESTRE — SISTEMA DE ORGANIZAÇÃO FINANCEIRA`
- Google Drive: `10_SISTEMA_ORGANIZACAO_FINANCEIRA`
- Codex: esta pasta
- Código remoto: [HugoMota-IMD/SISTEMA-DE-ORGANIZA-O](https://github.com/HugoMota-IMD/SISTEMA-DE-ORGANIZA-O), privado confirmado em 11/11; sincronização da candidata autorizada por Hugo, sem deploy

## Piloto Neon e Render — 11/11/2026

A candidata `0.2.0-prep` separa migrações do serviço web: o Render recebe apenas `organiza_app` via pool, sem credencial migrator e sem migração automática no build/start. Os ensaios isolados em PostgreSQL 18.6 e PgBouncer verificam permissões, reutilização de conexões, migração/restauração fictícia e partida Linux. O banco oficial está preservado em C:. Destinos informados: Neon São Paulo e Render My Workspace / Free / Virginia. O repositório privado foi confirmado e Hugo autorizou sincronizar esta candidata com `main`, preservando o histórico remoto. Esquema Neon, importação real e deploy permanecem pendentes da aprovação final. [Registro da sincronização](docs/SYNC-MAIN-2026-11-11.md) · [Campos exatos e segredos](docs/PILOT-RENDER-CONFIG.md) · [Relatório técnico](docs/REPORT-V0.2-NEON-RENDER.md)

## Versão local V0.1

**0.1.3 — acesso privado Tailscale ativo (29/10/2026):** **https://desktop-flde4sk.tail08d4d6.ts.net/**, com Tailscale conectado. Backend preservado em localhost, origem HTTPS específica, cookies privados seguros, iniciador sem duplicação e comandos de status/parada. Oito grupos de teste HTTPS real passaram com certificado válido e dados fictícios; a rota temporária foi removida. A máquina e a base existentes foram confirmadas em `C:`; a unidade `D:` informada não está disponível nesta sessão. Funnel permanece desativado. Falta homologar iPhone e dois computadores por outra rede. [Guia de acesso](docs/PRIVATE-ACCESS.md) e [relatório real da execução](docs/REPORT-V0.1.3-TAILSCALE.md).

Melhoria **0.1.2 — confirmação de pagamentos**: a ação Confirmar pagamento usa automaticamente o saldo pendente, confere a conta e a data e mostra os saldos antes/depois. Pagamento parcial é uma escolha secundária; parcelas do cartão encaminham para Pagar fatura. Valores originais, liquidados e devedores ficam separados. Inclui revalidação no servidor, antecipação explícita e estorno com histórico. Não exige migração de banco. [Relatório e roteiro de homologação](docs/REPORT-V0.1.2-PAYMENTS.md).

Correção **0.1.1 — cadastro de contas parceladas**: formulário exclusivo em três etapas, escolha explícita entre cartão e dívida fora do cartão, entrada por valor total ou valor da parcela, cronograma exato antes da confirmação e validações junto aos campos. Valores brasileiros como `1.000` e `1.000,00` são aceitos. A primeira fatura por mês preserva o dia do cartão após fevereiro. Não exige migração de banco; reinicie o servidor e atualize a página. [Relatório da correção](docs/REPORT-V0.1.1-INSTALLMENTS.md).

Aplicativo **Organiza**, para uso individual, em casal ou em família, com acessos pessoais e espaços financeiros separados. Implementado em Django 5.2 LTS, interface responsiva em português e banco SQLite no servidor. O comando V01, recebido em 19/10/2026, fundamenta esta primeira implementação.

Inclui contas, receitas, despesas Pix e outras formas, transferências próprias, cartões, faturas, parcelas, pagamentos parciais, estornos e ajustes rastreáveis; projeção de 12 a 60 meses na interface; simulação sem criar dívida; recorrências mensais, categorias e subcategorias, relatórios por base e período, orçamentos, alertas internos e participantes com três papéis. O motor usa centavos inteiros e preserva o total das parcelas.

### Abrir o aplicativo

Execute na raiz exclusiva deste projeto:

```powershell
powershell -File .\start.ps1
```

Abra `http://127.0.0.1:8765`. Esta instalação já possui banco existente: entre com seu acesso. O iniciador valida a instalação e o banco, inicia em segundo plano e reconhece um servidor já ativo. Não cria banco vazio, não reinstala dependências e não aplica migrações automaticamente. Não há senha padrão. Para consultar ou parar somente o Organiza, use `powershell -File .\status.ps1` e `powershell -File .\stop.ps1`. Operação detalhada: [manual](docs/MANUAL.md).

### Verificar

```powershell
.\.venv\Scripts\python.exe manage.py test finance --verbosity 1
.\.venv\Scripts\python.exe tools\verify_restore.py
```

Regressão específica de parcelamentos: `node tools/test_finance_input.cjs` e `.\.venv\Scripts\python.exe tools\verify_installments.py` (este último usa as dependências de navegador já descritas abaixo e uma base fictícia isolada).

Confirmações de pagamento: `.\.venv\Scripts\python.exe tools\verify_payments.py` testa a interface em base fictícia; `.\.venv\Scripts\python.exe tools\verify_payments_concurrency.py` verifica duas confirmações HTTP simultâneas, também sem acessar o banco de uso.

O ensaio visual isolado usa `requirements-dev.txt`, Playwright e Chromium instalado dentro de `.browser-cache`. Depois de instalar essas dependências, execute `tools\verify_ui.py`. Evidências e bases fictícias ficam em `test-results`, fora do Git. Consulte os comandos e resultados em [estado atual](docs/CURRENT-STATE.md).

### Documentação

- [Requisitos V01](docs/REQUIREMENTS.md), [backlog](docs/BACKLOG.md) e [critérios de aceite](docs/ACCEPTANCE.md).
- [Arquitetura e decisões](docs/ARCHITECTURE.md), [modelo financeiro](docs/FINANCIAL-MODEL.md) e [manual](docs/MANUAL.md).
- [Estado atual](docs/CURRENT-STATE.md) e [relatório ao COMANDO MESTRE](docs/REPORT-V0.1.md).

### Limites desta versão

A validação técnica inclui HTTPS privado real por Tailscale Serve, com backend somente em localhost. Google Cloud está adiado; não há publicação pública. Homologação no iPhone e nos dois computadores adicionais, incluindo outra rede, permanece pendente. O servidor precisa permanecer ligado, sem suspensão, com internet e Tailscale ativo. Não há edição offline, integração bancária, push, recuperação de senha por e-mail nem juros bancários calculados automaticamente. Consulte o manual e o estado atual antes de usar.

Os dados financeiros ficam em `data/finance.sqlite3`; não ficam apenas no navegador. `.env`, banco, backups, chave local de sessões e evidências são ignorados pelo Git. O backup pode ser restaurado para um novo arquivo, sem sobrescrever a origem.

## Fluxo obrigatório

1. Registrar requisitos e decisões no COMANDO MESTRE.
2. Executar mudanças nesta pasta pelo Codex.
3. Testar e documentar o resultado.
4. Atualizar `docs/CURRENT-STATE.md`.
5. Levar o resumo da execução de volta ao COMANDO MESTRE.
