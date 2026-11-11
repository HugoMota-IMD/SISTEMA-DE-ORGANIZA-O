# Arquitetura e decisões — V0.1

## Preparação hospedada 0.2.0-prep

A candidata preserva o modelo financeiro em centavos e a autenticação Django. O serviço web pode ser substituído mantendo usuários, sessões, associações, documentos e operações no PostgreSQL. Cada transação financeira identifica o ator da requisição. Filtros de associação e gatilhos validam espaço, papel, autoria e revisão. A proteção pressupõe credenciais de gestão controladas pelo operador.

O Render executará Gunicorn e WhiteNoise. Conexões da aplicação admitem o pool do Neon. Esquema, importação e backups usam conexão direta. O processo web expõe saúde sem consulta ao banco. A configuração de segredos, origens HTTPS, TLS, cadastro e manutenção inicial consta no [roteiro de implantação](HOSTING-NEON-RENDER.md). O SQLite em C: segue como base oficial até o corte.

Data: 19/10/2026. Responsável pelas decisões de produto: Hugo Erazo.

## Diagnóstico confirmado

Chat `CODEX — ORGANIZAÇÃO FINANCEIRA`. Raiz Git exclusiva confirmada: `C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA`. Antes desta execução existiam apenas AGENTS.md, README.md, .gitignore e docs/CURRENT-STATE.md, todos ainda sem commit. Nenhum remoto foi encontrado. Não existe aplicação anterior a substituir. Os materiais existentes serão preservados.

## Decisões anteriores à implementação

1. Aplicação web responsiva em português, com HTML/CSS/JavaScript sem dependências de interface ou serviços externos. Manifesto de instalação, sem edição offline e sem cache de dados financeiros.
2. Python 3.14 disponível na máquina; Django 5.2 LTS, com versão de correção resolvida e fixada depois da instalação. A série tem suporte estendido até abril de 2028 e suporta Python 3.14 desde 5.2.8. Waitress fornece WSGI compatível com Windows. Fontes: [Django](https://www.djangoproject.com/download/), [compatibilidade](https://docs.djangoproject.com/en/5.2/releases/5.2/), [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/).
3. SQLite no servidor, sessões autenticadas Django, senhas derivadas pelo framework, proteção CSRF, consultas filtradas por associação ao espaço e papéis administrador/colaborador/leitor. Cada pessoa usa credenciais próprias. Nenhum acesso familiar implícito.
4. Um documento financeiro JSON por espaço, persistido em registro com chave estrangeira única para esse espaço. Entidades financeiras usam identificadores internos ao documento; referências são validadas dentro dele. É uma escolha inicial para volume pessoal/familiar, com domínio independente do banco. Histórico e chaves de idempotência são tabelas separadas. Migração relacional/PostgreSQL pode ser feita preservando IDs quando o volume justificar.
5. Autorização no servidor e no banco: associações únicas usuário/espaço, chaves estrangeiras, controle de revisão, transações e gatilhos SQLite consultam o ator da conexão e rejeitam gravações financeiras sem papel autorizado. Leituras usam filtro de associação em SQL. Isso não equivale a RLS PostgreSQL ou isolamento contra o administrador do arquivo SQLite; a conta do serviço e os backups precisam de proteção operacional.
6. Valores inteiros em centavos. Compra é a classificação de consumo; obrigação é a fonte única da dívida; fatura apenas agrega obrigações. Pagamento gera liquidação e movimento de caixa, sem nova despesa de consumo. Saldo realizado, saldo devedor e compromisso mensal permanecem conceitos distintos.
7. Operações financeiras recebem chave idempotente e revisão esperada. A transação grava estado e histórico juntos. Revisão desatualizada resulta em conflito, sem sobrescrever outro dispositivo. Estornos e ajustes deixam registros próprios.
8. Backup usa a API de backup SQLite, inclui usuários, associações, sessões e histórico e deve ser guardado como dado sensível. Restauração somente para arquivo novo, com verificação de integridade e teste de leitura. Segredos e banco não entram no Git.

## Operação, hospedagem e custos

Atualização de 29/10/2026: Google Cloud adiado. O destino privado solicitado é o computador existente DESKTOP-FLDE4SK, IP Tailscale confirmado 100.108.133.59, com backend 127.0.0.1:8765 e uma única base SQLite oficial. A fonte e o banco continuam em C: nesta máquina; D: não está disponível. **Tailscale Serve ativo em HTTPS 443 → 127.0.0.1:8765**, endereço https://desktop-flde4sk.tail08d4d6.ts.net/. A liberação administrativa inicial foi resolvida. Oito grupos HTTPS reais passaram com dados fictícios pela rota temporária 8443, removida depois; a rota oficial foi verificada somente em leitura e abriu no navegador. Não há Funnel, encaminhamento de roteador ou abertura de firewall. O trecho abaixo registra as condições históricas da entrega inicial; a operação atual está detalhada em [PRIVATE-ACCESS.md](PRIVATE-ACCESS.md).

O proxy autorizado termina TLS e encaminha HTTP por loopback. Waitress aceita somente X-Forwarded-Proto do proxy 127.0.0.1; Django usa o esquema WSGI e não confia novamente no cabeçalho bruto ou em X-Forwarded-Host. Host e origem CSRF são exatos. No host privado, o middleware externo mantém autenticação/CSRF Django, usa cookies organiza_sessionid/organiza_csrftoken com Secure e HSTS sem incluir subdomínios. O acesso HTTP local mantém seus cookies anteriores. Nenhuma autenticação automática por identidade Tailscale substitui o acesso individual ao Organiza.

Validação inicial apenas nesta máquina, em localhost. Banco de servidor permite persistência independente do navegador. Dois clientes autenticados podem compartilhar o mesmo servidor. O acesso efetivo pelo celular, TLS, domínio, serviço permanente e acesso pela internet dependem de destino e condições aprovados; não serão ativados nesta tarefa. Não há custo recorrente de licença ou serviço contratado nesta fase; energia, backup e eventual hospedagem são custos operacionais ainda não cotados. Não há promessa de hospedagem gratuita permanente.

Referência orçamentária consultada em 19/10/2026, sem contratação: um [Droplet Basic de 1 GiB](https://www.digitalocean.com/pricing/droplets) custa US$ 6/mês; [backup semanal de máquina](https://docs.digitalocean.com/products/backups/details/pricing/) acrescenta 20%, resultando em aproximadamente US$ 7,20/mês. É referência para servidor pequeno, não dimensionamento homologado; domínio, impostos, câmbio, armazenamento adicional e backup externo cifrado podem aumentar o total. Backup de máquina não substitui o backup consistente SQLite implementado. O destino e o orçamento final ainda serão aprovados por Hugo.

Uma futura publicação exige HTTPS, DEBUG desativado, hosts e origens explícitos, chave secreta externa, cookies seguros, backup fora da máquina, processo WSGI supervisionado, atualização de dependências e Git privado aprovado. Não há integração bancária, push, WhatsApp ou serviço de envio de e-mails nesta versão.

## Limites da entrega local

Não é a entrega oficial publicada. Sincronização remota do código e documentação oficial no Drive aguardam aprovação. Nenhuma escrita no Drive ocorrerá antes da confirmação explícita da conta `imd.hugo@dasemper.com` e do destino. Requisitos e critérios de aceite ficam nos documentos complementares desta pasta. Resultados efetivos serão registrados no estado atual ao concluir os testes.
