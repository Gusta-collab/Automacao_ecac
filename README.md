# Automação Fiscal — e-CAC

Aplicativo desktop em Python para organizar documentos fiscais de clientes, consultar dados públicos de CNPJ, conferir arquivos SPED e captar documentos no e-CAC por meio de uma sessão do Google Chrome autenticada manualmente.

## Funcionalidades

- Consulta de CNPJ pela API pública do [CNPJá](https://open.cnpja.com/), com registro da data de abertura e do histórico do Simples Nacional.
- Conferência de arquivos `.txt` de EFD ICMS/IPI, EFD Contribuições, ECF e ECD pelo período do registro `0000`, com indicação de períodos faltantes quando há uma data inicial disponível.
- Captação dos módulos **DCTF Normal**, **PER/DCOMP**, **PGDAS** e **DCTF-Web** na pasta do cliente selecionado. O seletor permite executar um módulo ou todos os quatro.
- Relatório local `RELATORIO_DOCUMENTOS.txt` com dados do cliente, resultados das captações, conferência de SPEDs e inventário dos arquivos da pasta.
- Conferência de itens em `PLANILHAS MA` pela identificação no nome dos arquivos e pastas. A compactação das subpastas de `DOCUMENTOS` é opcional.

## Requisitos e instalação

- Windows e Python 3.11 ou superior.
- Google Chrome instalado em `Program Files` ou `Program Files (x86)`.
- Acesso ao e-CAC com certificado digital válido e procuração eletrônica para os CNPJs atendidos.
- Conexão à internet para consultar o CNPJá e acessar o e-CAC.

No PowerShell, na pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python Master_Automacao.py
```

As dependências Python estão em `requirements.txt`: CustomTkinter, Requests e Selenium. O Selenium conecta ao Chrome aberto pelo aplicativo.

## Como usar

1. Em **Ajustes**, defina, se desejar, a pasta temporária de downloads, uma pasta modelo para copiar aos novos clientes e a pasta padrão de clientes. As preferências são salvas em `%LOCALAPPDATA%\Automacao_Fiscal\config.json`.
2. No passo **01**, crie uma pasta de cliente ou selecione uma existente. Sem pasta padrão configurada, novos clientes ficam em `CLIENTES/` ao lado do script. O aplicativo cria `SPEDS/EFD-ICMS IPI`, `SPEDS/EFD-Contribuicoes`, `SPEDS/ECF` e `SPEDS/ECD`.
3. Para conferir SPEDs, coloque cada arquivo `.txt` na subpasta correspondente. Informe o CNPJ com 14 dígitos e clique em **Consultar** para registrar abertura e Simples Nacional. Depois clique em **Verificar SPEDs**. Sem consulta, o relatório lista os períodos encontrados, mas não calcula faltantes; para optantes atuais do Simples, os períodos esperados não são aplicados.
4. Para captar documentos, selecione um módulo no passo **02**. Clique em **Chrome**, conclua o login no e-CAC na janela aberta pelo aplicativo e escolha manualmente o perfil do cliente no portal. Confirme que o perfil ativo corresponde à pasta selecionada.
5. Clique em **Iniciar**. O Selenium se conecta à sessão autenticada e salva os documentos na pasta do cliente criado ou selecionado no passo **01**. Confira o registro de atividades e os arquivos baixados após a execução.
6. Para a conferência final, coloque os arquivos a verificar em `PLANILHAS MA` dentro da pasta do cliente e clique em **Finalizar**. O resultado é registrado no relatório.

## Arquivos e cuidados

- A conferência de SPEDs lê o período do registro `0000`; a conferência de `PLANILHAS MA` procura identificadores nos nomes. Nenhuma das duas valida integralmente o conteúdo fiscal. Revise os resultados manualmente.
- Se `Rar.exe` estiver no `PATH`, **Finalizar** compacta cada subpasta de `DOCUMENTOS` em `.rar` e preserva os arquivos de origem. Sem `Rar.exe`, a conferência ainda é executada.
- A automação depende das telas atuais do e-CAC e de uma sessão autenticada. Mudanças no portal ou indisponibilidade podem interromper uma captação; confirme os downloads no relatório e na pasta do cliente.
- Dados e documentos fiscais são gravados localmente. O CNPJ informado é enviado à API pública do CNPJá durante a consulta. Antes de publicar alterações no GitHub, confira `git status` e os arquivos incluídos no commit; mantenha certificados, credenciais e dados de clientes fora do repositório. O `.gitignore` cobre os artefatos locais mais comuns, incluindo `CLIENTES/`.