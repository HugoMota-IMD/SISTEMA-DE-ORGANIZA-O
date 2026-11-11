# Retorno ao COMANDO MESTRE — Organiza e acesso privado Tailscale

Data: **29/10/2026** · Versão: **0.1.3** · Situação: **HTTPS privado ativo e tecnicamente testado; pendente homologação nos três dispositivos clientes por outra rede**.

## Servidor, raiz e banco confirmados

- Máquina: **DESKTOP-FLDE4SK**, o mesmo computador com IP Tailscale **100.108.133.59** informado por Hugo.
- Tailscale instalado: **1.104.4**, estado Running/online, MagicDNS ativo. Um iPhone estava online; isso não equivale a teste físico do Organiza. Os outros dois computadores não foram configurados nesta execução.
- Fonte e raiz Git efetivamente utilizadas: `C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`.
- Banco configurado, estrutura SQLite e caminho nos metadados do processo confirmados: `C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA\data\finance.sqlite3`.
- O caminho novo em **D:** não existe nesta sessão, e essa unidade não está disponível. Não foi presumida a migração, criado substituto, copiado banco ativo ou movida a instalação.

AGENTS.md local, README, estado, configuração e Git foram conferidos antes das alterações. A aplicação encontrada era **0.1.2**, com banco existente e servidor parado. Git permanece sem commits e sem remoto; alterações anteriores foram preservadas. O motor financeiro e a interface de pagamentos/parcelamentos não foram modificados.

## Preservação

Antes de modificar a configuração, foi feito backup consistente pela API SQLite e verificada sua integridade, sem sobrescrever destino:

`backups/finance-before-tailscale-20261029-135121.sqlite3`.

Antes de ativar as rotas após a liberação, foi feito novo backup consistente verificado: `backups/finance-before-serve-activation-20261029-160313.sqlite3`.

Nenhum banco foi apagado, reinicializado, substituído ou migrado. Testes de gravação usaram somente bases fictícias separadas. O banco oficial permaneceu com assinatura SHA-256 idêntica durante a execução, inclusive após parada e novo início oficiais. Foi confirmado que o processo atual não está elevado e o backend está somente em loopback. Fonte, chave local de sessões, registros e configurações existentes foram preservados. `.env`, banco, logs, backups e evidências continuam ignorados pelo Git. Não houve inspeção de dados pessoais para elaborar relatórios.

## Configurações implementadas

1. **Backend:** Waitress continua restrito a **127.0.0.1:8765**, sem bind em rede geral ou IP Tailscale. Com origem privada configurada, aceita somente X-Forwarded-Proto do proxy loopback e traduz para o esquema WSGI; outros cabeçalhos encaminhados continuam descartados. Django não confia novamente em X-Forwarded-Proto bruto nem em X-Forwarded-Host. [Waitress oficial](https://docs.pylonsproject.org/projects/waitress/en/latest/reverse-proxy.html).
2. **Django:** `APP_PRIVATE_HTTPS_ORIGIN` valida origem HTTPS exata `.ts.net`, sem wildcard, caminho ou credenciais; adiciona apenas esse host/origem CSRF. No hostname privado, cookies de sessão/CSRF recebem nomes exclusivos, Secure e SameSite Strict, mantendo a proteção CSRF e sessão individual. HSTS não inclui subdomínios. O acesso HTTP loopback conserva os cookies anteriores e continua funcionando. [Configuração Django](https://docs.djangoproject.com/en/5.2/ref/settings/).
3. **Operação:** start/status/stop verificam identidade, raiz, porta e banco existentes, sem reinstalação ou migração automática. Locks impedem dois iniciadores ou execução direta duplicada. A parada só encerra o Python confirmado deste Organiza; processos externos em conflito são recusados. Logs locais não contêm senhas ou corpos financeiros.
4. **Tailscale:** configuração atual foi lida antes da tentativa; não existiam rotas Serve/Funnel nem Services de outros projetos. O helper preparado salva snapshot, valida o nó, recusa raiz/TCP/Funnel em conflito, compara outros serviços e altera somente seu endpoint. Não existe reset global, clear, comando Funnel ou mudança de firewall/roteador nessa operação. [CLI oficial](https://tailscale.com/docs/reference/tailscale-cli/serve).
5. **Inicialização automática:** opção reversível em HKCU Run no logon do próprio usuário, sem solicitar administrador, com caminho e banco desta instalação e bloqueio de duplicação. **Permanece desativada.** Não foi alterado Run unattended do Tailscale, política global de scripts, energia ou suspensão.

A configuração `.env` local recebeu somente a origem privada exata; não foram adicionadas credenciais. A arquitetura mantém uma aplicação e um banco oficiais para servidor, dois computadores clientes e iPhone. As pessoas continuam com contas próprias no Organiza e permissões por espaço; Tailscale não concede automaticamente associação a espaços.

## Bloqueio inicial resolvido e link ativo

Local, já verificado: **http://127.0.0.1:8765/**.

Privado **ativo e verificado**: **https://desktop-flde4sk.tail08d4d6.ts.net/**, com Tailscale conectado. Configuração oficial: HTTPS 443 → http://127.0.0.1:8765, somente tailnet, sem Funnel.

A tentativa inicial retornou **“Serve is not enabled on your tailnet.”**. A página exigiu login administrativo e as primeiras tentativas não aplicaram rota. Hugo depois mostrou a tela **“Serve está pronto para usar”**, com a opção Funnel desmarcada. A nova tentativa foi aceita. Foi configurada a rota temporária HTTPS 8443 → backend fictício 8771; os oito grupos HTTPS reais passaram com certificado validado, e o script encerrou seu backend. Somente a rota temporária 8443 foi removida. Depois foi aplicada e verificada a rota oficial 443, preservando outros serviços e sem Funnel. A tela de login oficial abriu no navegador pelo HTTPS, sem alerta de certificado.

**A intervenção administrativa já está resolvida; não é necessário habilitar Funnel nem repetir o passo inicial.** As referências para eventual recuperação são [HTTPS oficial](https://tailscale.com/docs/how-to/set-up-https-certificates) e [Serve privado](https://tailscale.com/docs/features/tailscale-serve).

Para consultar ou reaplicar a configuração já ativa, na raiz confirmada:

```powershell
powershell -NoProfile -File .\start.ps1
.\.venv\Scripts\python.exe tools\configure_tailscale.py check
.\.venv\Scripts\python.exe tools\configure_tailscale.py apply
.\.venv\Scripts\python.exe tools\configure_tailscale.py check --verify
```

Se em manutenção futura o sistema exigir elevação local para configurar Serve, executar apenas essa etapa em terminal administrativo. O iniciador do backend não pede elevação. A conferência HTTPS e o ensaio autenticado em base fictícia foram concluídos. A rota de teste 8443 e o backend 8771 não permaneceram disponíveis; somente a rota oficial 443 está ativa.

## Testes e resultados reais

| Verificação | Resultado |
|---|---|
| `manage.py test finance --verbosity 1` | **134 aprovados:** 126 anteriores + 8 novos de acesso privado |
| `finance.test_private_access` | Cookies privados Secure e nomes próprios, login/logout local e privado, Host, CSRF, origem, redirecionamento, papéis e espaços aprovados no cliente de teste Django; HTTPS simulado, sem certificado real |
| `tools/verify_private_access.py` | **8 grupos HTTP aprovados**, banco fictício, ações autenticadas, concorrência 200/409 e reenvio sem duplicação; estado/sessões completos iguais após reinício real com mudança de PID comprovada |
| `tools/verify_private_access.py --base-url https://desktop-flde4sk.tail08d4d6.ts.net:8443 --port 8771` | **8 grupos HTTPS reais aprovados**, certificado validado sem bypass, cookies Secure/HSTS, login/logout, CSRF, perfis/espaços, pagamentos parciais/restante, concorrência 409/200, reenvio idempotente e persistência após reinício |
| `tools/verify_runtime.py` | **6 grupos aprovados:** estados Serve, banco ausente sem criação, dois iniciadores/um servidor, execução direta duplicada, parada/reinício preservando estado e recusa de serviço externo sem encerrá-lo |
| `python -m unittest tools.test_tailscale_config` | **18 testes aprovados**, CLI/rede simulados; conflitos, Funnel, TCP alheio, host exato, preservação de Services e outros caminhos/portas, timeout, idempotência e remoção escopada |
| `tools/verify_ui.py` | Fluxo geral, segunda sessão, projeção 12/60 meses e simulação aprovados; computador 1440×1000 e celular emulado 390×844, zero erros/overflow |
| `tools/verify_restore.py` | Snapshot completo igual em outro processo, administrador/leitor, integridade, projeção e recusa de sobrescrita aprovados |
| `node tools/test_finance_input.cjs` | **33 verificações aprovadas** |
| Configuração e dependências | `manage.py check`, `makemigrations --check --dry-run`, `pip check`, sintaxe Python/JavaScript/PowerShell aprovados; nenhuma migração nova |
| Origem inválida | HTTP, wildcard, porta zero e caminho recusados |
| Instalação oficial em leitura | Página HTTP 200, health 0.1.3, backend somente 127.0.0.1 e banco exato nos metadados; segunda execução não duplicou processo |
| HTTPS oficial | Helper `check --verify` confirmou identidade desta instalação em HTTP/HTTPS; tela de login abriu no navegador, sem alerta de certificado |
| Aparelhos físicos e outra rede | **Pendentes**, sem execução ou confirmação de Hugo |

Evidências locais ignoradas pelo Git: `test-results/private-access-http-evidence.json`, **`private-access-https-evidence.json`**, `runtime-evidence.json`, `ui-evidence.json`, `restore-evidence.json`, `tailscale-local-status.json`, `tailscale-private-status.json`, `tailscale-serve-before.json`, `tailscale-preservation-before.json`, `tailscale-preservation-result.json`, **`tailscale-active-private-status.json`**, `tailscale-activation-before.json` e `tailscale-activation-result.json`. O ensaio HTTP registra `tls_certificate_verified: false`; o novo ensaio HTTPS real registra **true**, com banco fictício e proxy efetivo. A ativação oficial foi conferida sem gravações financeiras de teste.

## Iniciar, parar e usar

```powershell
powershell -NoProfile -File .\start.ps1
powershell -NoProfile -File .\status.ps1
powershell -NoProfile -File .\stop.ps1
```

Todos executados na raiz confirmada. O backend fica em segundo plano; fechar terminal não o encerra. Status diferencia conexão Tailscale de rota Serve pronta. Sem política para executar PowerShell, usar o Python local com `tools/organiza_runtime.py start|status|stop`, sem enfraquecer política global.

Autostart opcional: `powershell -File .\tools\configure_autostart.ps1 -Enable`; desfazer com `-Disable`. Essa opção depende de logon e de política local que aceite os scripts. A consulta sem flags confirmou **desativada**.

Nos clientes: instalar Tailscale oficial, conectar à tailnet autorizada, abrir o HTTPS ativo e entrar com a conta individual do Organiza. Criar atalho no navegador/Windows ou adicionar à Tela de Início pelo Safari. **Não instalar Python nem copiar banco nos clientes.** Desenvolvimento em outro PC exige remoto Git privado aprovado e banco fictício separado; nenhum remoto/push foi feito aqui.

## Dependências e homologação

O servidor deve permanecer ligado, sem suspensão, conectado à internet e com Tailscale ativo para acesso de outra rede. Autostart no logon não mantém máquina acordada nem inicia antes do login do usuário. Nenhuma configuração de energia foi alterada.

Com a habilitação e o ensaio HTTPS real concluídos, Hugo deve agora validar no iPhone e nos dois computadores: certificado sem alertas, login/logout individual, papéis e espaços, gravação em espaço fictício, atualização simultânea sem pagamento duplicado, persistência após reinício e uso por outra rede. No iPhone, repetir com Wi-Fi desligado e dados móveis/Tailscale ativos. Nada disso foi declarado executado em aparelhos físicos.

Guia completo: **docs/PRIVATE-ACCESS.md**. A homologação anterior de parcelas/pagamentos por Hugo continua integrada a esse roteiro; não se presume concluída apenas porque a suíte técnica passou.

## Arquivos desta entrega

Existentes modificados, todos dentro da raiz confirmada:

```text
.env.example
README.md
config/settings.py
config/urls.py
finance/views.py
serve.py
start.ps1
docs/ARCHITECTURE.md
docs/CURRENT-STATE.md
docs/MANUAL.md
```

Novos:

```text
finance/access.py
finance/test_private_access.py
stop.ps1
status.ps1
tools/organiza_runtime.py
tools/runtime_lock.py
tools/configure_autostart.ps1
tools/verify_runtime.py
tools/verify_private_access.py
tools/configure_tailscale.py
tools/test_tailscale_config.py
docs/PRIVATE-ACCESS.md
docs/REPORT-V0.1.3-TAILSCALE.md
```

Configuração local ignorada alterada: `.env`, somente origem privada. Artefatos ignorados gerados: backup consistente, logs/metadados/locks próprios em `data/runtime` e evidências/bases fictícias em `test-results`. Não houve alteração de outro projeto, migração de banco, configuração de firewall/roteador, publicação pública, push ou escrita no Drive. A abertura da página de login administrativo não concedeu permissões nem criou sessão autenticada.

## Pendências e próxima ação

**Próxima ação:** homologar o endereço HTTPS ativo no iPhone e nos dois computadores, incluindo outra rede. A liberação administrativa, configuração Serve e ensaios HTTPS reais estão concluídos. Autostart permanece opcional/desativado; Google Cloud continua adiado. Nenhuma credencial foi armazenada em código ou relatório.

Na continuação da ativação foram alterados somente README.md e docs/CURRENT-STATE.md, PRIVATE-ACCESS.md, MANUAL.md, ARCHITECTURE.md e este relatório, além da configuração Serve escopada e dos artefatos locais ignorados. Nenhum código financeiro ou dado oficial foi alterado para executar os testes.
