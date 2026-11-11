# Retorno ao COMANDO MESTRE — Sistema de Organização Financeira

Data: 19/10/2026. Responsável pelas decisões: Hugo Erazo.

## Etapa e versão

**V0.1.0 local funcional (Organiza V01).** Diagnóstico/especificação concluídos e fluxo central implementado/testado. Participantes, relatórios, orçamento, alertas internos e simulação também implementados localmente. Homologação humana e entrega oficial publicada permanecem pendentes.

Raiz exclusiva efetivamente utilizada e confirmada pelo Git:
`C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`.

## Realizado e decisões

O projeto tinha apenas documentos iniciais, sem aplicação anterior a substituir. Foram lidos AGENTS.md, README.md, estado atual, comando V01 e guia de integração no Drive. Título do chat e raiz Git confirmados antes de alterações. O guia foi lido pela conta autorizada; não houve escrita no Drive.

Foi construído um aplicativo em português com acessos individuais, espaços pessoal/familiar, três perfis, contas, receitas, despesas/Pix, transferências, cartões, faturas, parcelas, pagamentos parciais, estornos, descontos/encargos/reembolsos e histórico. Inclui projeção extensível, simulação sem criar dívida, recorrências mensais, categorias/subcategorias editáveis, relatórios mensais por base, orçamento e alertas internos. O banco de uso começa vazio, sem senha padrão.

Django 5.2.18 LTS, Python 3.14.6, SQLite e Waitress 3.0.2 mantêm autenticação e persistência no servidor com poucas dependências e sem contratar serviço externo. Documento financeiro por espaço, associações explícitas, consultas filtradas, gatilhos, revisão e idempotência atendem à escala inicial. SQLite não oferece RLS PostgreSQL nem proteção contra o administrador do arquivo. A evolução para múltiplos servidores deve reavaliar o armazenamento.

Compra classifica consumo; obrigações representam dívida; faturas apenas agregam. Pagamento liquida e movimenta caixa sem duplicar despesa. Valores são centavos inteiros. Saldo, dívida, compromisso mensal e projeção são distintos. Previsões futuras de recorrências não inflam a dívida ao ampliar o horizonte.

## Testes e resultados

**74 testes aprovados:** 57 de regras financeiras e 17 de API/segurança. Incluem R$ 285 em Alimentação, R$ 1.000 em três parcelas exatas, compromisso R$ 1.000 → R$ 850 após última parcela de R$ 150, atraso sem quitação, fatura sem duplicação, parcial, transferências, cartões distintos, dívida anterior, cancelamento/estorno/antecipação, datas/mês/ano, isolamento, perfis, CSRF, autoria, idempotência e concorrência.

Migrações sem divergência, dependências consistentes, sintaxe JavaScript e checks sem problemas. A checagem para futura hospedagem usou configuração de teste; não houve implantação.

Navegador: criar acesso/espaço/conta/cartão → receber receita → pagar Pix → compra parcelada → fatura parcial → projeção/simulação. Duas sessões independentes em 1440×1000 e 390×844, sem erros de console nem transbordamento. Simulação não alterou o estado persistido. Não foi usado aparelho físico.

Restauração: snapshot completo idêntico em outro processo, login de administrador/leitor, integridade e recusa de sobrescrita. Fixture contém 2 usuários, 2 contas, cartão, 8 lançamentos, 9 obrigações, 3 pagamentos, 5 movimentos de caixa, recorrência, orçamento, auditoria e projeção. Saldo 153456 centavos e dívida 92000 centavos preservados. Somente dados fictícios. Evidências em test-results/ui-evidence.json e restore-evidence.json, fora do Git; detalhes em docs/CURRENT-STATE.md.

## Arquivos alterados nesta raiz

Existentes modificados: `.gitignore`, `README.md`, `docs/CURRENT-STATE.md`.

Novos arquivos de aplicação/configuração/testes:

```text
.env.example
manage.py
requirements.txt
requirements-dev.txt
serve.py
start.ps1
config/__init__.py
config/settings.py
config/urls.py
config/wsgi.py
finance/__init__.py
finance/apps.py
finance/domain.py
finance/models.py
finance/security.py
finance/views.py
finance/test_api.py
finance/test_domain.py
finance/migrations/__init__.py
finance/migrations/0001_initial.py
finance/migrations/0002_database_guards.py
templates/index.html
static/app.js
static/app.css
static/icon.svg
static/manifest.webmanifest
tools/__init__.py
tools/backup.py
tools/verify_restore.py
tools/verify_ui.py
```

Novos documentos:

```text
docs/EXECUTION-COMMAND-V01.txt
docs/REQUIREMENTS.md
docs/BACKLOG.md
docs/ACCEPTANCE.md
docs/ARCHITECTURE.md
docs/FINANCIAL-MODEL.md
docs/MANUAL.md
docs/REPORT-V0.1.md
```

AGENTS.md foi preservado sem alteração, embora já estivesse sem commit. `.venv`, `.browser-cache`, data, backups e test-results são artefatos locais ignorados: dependências, chave local, base de uso vazia e fixtures/evidências fictícias. Nenhum arquivo de outro projeto foi alterado ou descartado.

## Pendências, Git e próxima ação

Homologação por Hugo/família, aparelhos reais, hospedagem/HTTPS, serviço permanente, backup externo cifrado e Git privado remoto. Confirmar expressamente conta `imd.hugo@dasemper.com` e destino antes de qualquer escrita da documentação oficial no Drive.

Recorrências mensais de valor conhecido, término opcional no cadastro, ainda sem ação dedicada para interromper uma já criada. Sem rateio familiar automático, exportação de relatórios, intervalo arbitrário, recuperação de senha por e-mail, integração bancária, push ou juros contratuais estimados. Reembolsos já devolvidos podem exigir correção específica em vez de estorno integral. Relatórios reclassificam ajustes na base da compra e preservam o histórico, sem contabilidade bitemporal.

Git local iniciado, ainda sem commits e sem remoto. Não houve commit, push, criação de repositório externo, publicação ou implantação. Código e banco ainda dependem desta máquina; a entrega oficial requer sincronização privada aprovada e documentação no destino confirmado.

**Próxima ação:** homologar em `http://127.0.0.1:8765`, conforme docs/MANUAL.md, usando dados fictícios. Depois aprovar destino de hospedagem, condições/custos, Git privado e destino documental para preparar publicação e verificar aparelhos reais. Novas decisões devem ser registradas no COMANDO MESTRE e encaminhadas ao projeto operacional.
