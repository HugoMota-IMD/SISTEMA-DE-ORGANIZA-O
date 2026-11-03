# Organiza — Sistema de Organização Financeira

Aplicativo de organização financeira para uso individual, em casal ou em família.

## Funcionalidades documentadas na versão local

- Contas, receitas, despesas e transferências próprias.
- Cartões, faturas e compras parceladas.
- Pagamentos integrais e parciais, estornos e histórico rastreável.
- Projeções financeiras, simulações, recorrências e orçamentos.
- Espaços financeiros separados e participantes com diferentes papéis.

## Tecnologias

Python, Django 5.2 LTS e SQLite, com interface responsiva em português. O motor financeiro usa centavos inteiros e preserva o total das parcelas.

## Estado do projeto

A documentação local registra a versão **0.1.3**, com acesso privado e homologação em dispositivos adicionais pendente. A preparação de uma futura hospedagem não equivale a uma migração ou publicação concluída.

O código-fonte da versão local foi importado em 03/11/2026, incluindo testes e migrações. Bancos, backups, ambiente local e relatórios operacionais privados foram excluídos.

## Próximas etapas

- Documentar instalação e validar os fluxos da versão importada em ambiente de teste.

[Portfólio de Hugo Mota](https://github.com/HugoMota-IMD)

Documentação organizada em 03/11/2026.

## Instalação para desenvolvimento

Use Python e um ambiente virtual. Instale `requirements.txt`, copie `.env.example` para `.env` e revise as opções locais. Em uma instalação nova, execute `python manage.py migrate`, `python manage.py createsuperuser` e `python manage.py runserver 127.0.0.1:8765`. O banco criado será vazio e local. Não substitua uma instalação existente nem importe dados reais neste repositório.

Para testar: `python manage.py test finance`. Scripts de início preservam instalações existentes e podem exigir configuração adicional; o roteiro acima destina-se a uma cópia nova de desenvolvimento.
