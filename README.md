# Translate Screen Text

Aplicacao em Python para reconhecer textos exibidos em jogos, traduzi-los e
apresentar a traducao visualmente sobre a tela original.

O fluxo atual implementa captura, OCR, tradução e sobreposição visual
em uma região selecionada ou na tela inteira do monitor principal.

## Interface de controle e captura

Inicie o modo de captura:

```powershell
poetry run translate-screen capture
```

O comando abre a central de controle em PySide6, renderizada com HTML e CSS, e
inicia o capturador automaticamente. Pela tela principal é possível registrar
um novo atalho pressionando a combinação desejada, abrir o guia de funcionamento
e acessar as configurações. As preferências ficam salvas entre execuções.

Nas configurações podem ser definidos o idioma de destino, o formato da captura
(seleção de região ou tela inteira), o tema claro ou escuro (escuro por padrão)
e o comportamento ao minimizar: permanecer na barra de tarefas ou recolher para
a bandeja do Windows.
O botão de maximizar permanece desabilitado. Fechar a janela principal, usar a
opção `Encerrar` da bandeja ou pressionar `Ctrl+Shift+Q` encerra a interface, o
listener global e o processo de captura.

Com o programa em execução:

1. Pressione o atalho configurado em qualquer aplicativo (`F6` por padrão).
2. No modo de região, arraste o mouse sobre a área desejada e solte o botão.
   No modo de tela inteira, a captura acontece imediatamente.
3. A imagem temporária é salva em `output/captures`.
4. Um indicador animado informa que a imagem está sendo processada.
5. O OCR detecta as linhas e imprime o texto reconhecido no terminal.
6. O provedor selecionado traduz cada região reconhecida.
7. Uma janela transparente desfoca o texto original e exibe a tradução por cima.

O OCR e a tradução são executados em segundo plano, mantendo o indicador e a
interface responsivos até que o resultado esteja pronto.

O overlay permanece sempre no topo e não intercepta cliques do mouse. Ele é
removido ao pressionar ou soltar uma tecla, clicar com qualquer botão do mouse
ou usar um controle XInput. Mover o mouse ou usar o scroll não limpa a tela. O
overlay também é removido ao iniciar uma nova seleção com `F6` ou encerrar a
aplicação.
O texto traduzido é medido antes da renderização: frases longas são quebradas
em linhas e a fonte é reduzida até caber na região detectada pelo OCR.

`Esc` cancela a seleção. `Ctrl+Shift+Q` ou `Ctrl+C` encerra o programa.

Para executar apenas o capturador antigo, sem a central PySide6:

```powershell
poetry run translate-screen capture --headless
```

O modo também pode ser escolhido pela linha de comando. Sem a interface de
controle, `fullscreen` captura imediatamente o monitor principal ao pressionar
o atalho:

```powershell
poetry run translate-screen capture --headless --capture-mode fullscreen
```

## Tradução local com Argos Translate

O Argos traduz localmente, sem credenciais e sem acessar um serviço externo
durante a tradução. Na primeira execução, baixe o modelo do par de idiomas:

```powershell
poetry run translate-screen capture `
  --translator argos `
  --source-language en `
  --target-language pt-BR `
  --argos-install-model
```

Depois que o modelo estiver instalado, omita a opção de instalação:

```powershell
poetry run translate-screen capture --translator argos
```

Ao salvar pela interface um idioma cujo modelo Argos não esteja instalado, a
aplicação verifica o modelo antes de fechar as configurações e pergunta se deve
baixá-lo. A janela permanece aberta durante a verificação e a instalação. Se o
download for recusado, o idioma de destino volta automaticamente para Português
(Brasil) antes de a janela ser fechada.

O Argos não aceita `auto` como idioma de origem nesta integração. O código
`pt-BR` do CLI é convertido para o código `pb` usado pelo modelo brasileiro.

O Argos é o provedor padrão da aplicação. Portanto, a execução comum equivale
a iniciar com `--translator argos`.

## Executável para Windows

O build usa PyInstaller no formato `onedir` e inclui o ícone da aplicação, a
interface HTML/CSS, as dependências nativas e o modelo Argos `en -> pt-BR`.
Esse formato evita descompactar aproximadamente 84 MB de modelo a cada abertura
e permite que o processo de captura seja iniciado com rapidez.

Com Python 3.12 e Poetry instalados, execute na raiz do projeto:

```powershell
.\executable\build_windows.ps1
```

Na primeira geração, o script instala as dependências de desenvolvimento. Ele
reutiliza o modelo Argos já instalado; se o modelo não estiver disponível,
baixa o pacote durante o build. O resultado será criado em:

```text
executable\dist\TranslateScreenText\TranslateScreenText.exe
```

Distribua toda a pasta `executable\dist\TranslateScreenText`, não apenas o
arquivo `.exe`, pois `_internal` contém o modelo e as bibliotecas da aplicação.
Para builds seguintes, quando o ambiente Poetry já estiver atualizado, use:

```powershell
.\executable\build_windows.ps1 -SkipInstall
```

Acrescente `-Clean` quando quiser descartar o cache de análise do PyInstaller e
fazer uma reconstrução completa. Ao final de cada build, o script executa uma
tradução real de inglês para português com o `.exe`; o processo falha se o
modelo incorporado ou alguma biblioteca nativa estiver ausente.

O executável abre diretamente a interface de captura usando Argos. O modelo
incorporado funciona offline para inglês → português do Brasil; modelos de
outros idiomas continuam sendo instalados no perfil do usuário quando ele
confirma o download nas configurações.

## Tradução sem credenciais pela URL do Google

Para usar a integração não oficial, sem projeto ou credenciais do Google
Cloud, execute:

```powershell
poetry run translate-screen capture --translator google-url
```

O provedor consulta diretamente uma URL interna e não documentada do Google
Translate. Essa opção é adequada para protótipos, mas pode retornar HTTP 429,
sofrer limitações ou deixar de funcionar se o serviço mudar. O padrão da
aplicação é o Argos.

## Configuração do Google Cloud Translation

Antes de iniciar a tradução:

1. Crie ou selecione um projeto no Google Cloud.
2. Ative a Cloud Translation API e o faturamento do projeto.
3. Configure Application Default Credentials:

```powershell
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT="id-do-seu-projeto"
```

Depois, execute normalmente:

```powershell
poetry run translate-screen capture
```

Também é possível informar o projeto e os idiomas diretamente:

```powershell
poetry run translate-screen capture `
  --google-project id-do-seu-projeto `
  --source-language en `
  --target-language pt-BR
```

As credenciais não devem ser colocadas no código ou versionadas. Como alternativa
ao login do `gcloud`, `GOOGLE_APPLICATION_CREDENTIALS` pode apontar para um arquivo
de credenciais mantido fora do repositório.

Para executar somente o comportamento anterior, sem consumir a API:

```powershell
poetry run translate-screen capture --ocr-only
```

Outro diretório pode ser informado com:

```powershell
poetry run translate-screen capture --output-dir D:\capturas
```

O limite mínimo de confiança também pode ser configurado:

```powershell
poetry run translate-screen capture --ocr-confidence 0.65
```

Os eventos são exibidos como logs estruturados e identificam as etapas de
captura, OCR, tradução, overlay e limpeza. Depois que o overlay é apresentado,
o PNG temporário é excluído automaticamente. Para aumentar o detalhamento:

```powershell
poetry run translate-screen capture --translator argos --log-level DEBUG
```

Exemplo de saída:

```text
2026-09-19 14:30:00 | INFO | translate_screen_text.capture_ui | [ETAPA 1/5] Captura salva em: output\captures\capture_....png
2026-09-19 14:30:01 | INFO | translate_screen_text.capture_ui | [ETAPA 2/5] Texto detectado:
NEW GAME
CONTINUE
SETTINGS
2026-09-19 14:30:01 | INFO | translate_screen_text.capture_ui | [ETAPA 3/5] Tradução concluída (pt-BR):
NOVO JOGO
CONTINUAR
CONFIGURAÇÕES
2026-09-19 14:30:01 | INFO | translate_screen_text.capture_ui | [ETAPA 4/5] Overlay de tradução exibido.
2026-09-19 14:30:01 | INFO | translate_screen_text.capture_ui | [ETAPA 5/5] Captura temporária excluída.
```

Nesta primeira versão, a seleção cobre o monitor principal. Jogos em modo janela
ou janela sem bordas são preferíveis; tela cheia exclusiva pode impedir que o
seletor apareça.

## Fluxo principal

```text
imagem -> OCR -> regioes de texto -> traducao -> renderizacao -> imagem traduzida
```

O nucleo depende apenas de contratos. Bibliotecas de OCR, APIs de traducao e
ferramentas de renderizacao entram como adaptadores substituiveis.

## Estrutura

```text
src/translate_screen_text/
  assets/        # recursos usados em tempo de execução
  ui/            # páginas HTML e estilos da interface
  adapters/      # OCR, tradução, captura e overlays concretos
  *.py           # domínio, CLI, interface e orquestração
executable/
  assets/                    # ícone nativo do executável Windows
  build_windows.ps1          # orquestra o build e a validação final
  prepare_argos_model.py     # prepara o modelo en -> pt-BR
  translate_screen_text.spec # configuração do PyInstaller
  build/                     # cache e modelo preparados (gerado)
  dist/                      # distribuição final (gerada)
docs/
  architecture.md
tests/
  unit/
  integration/
  fixtures/
```

Os diretórios `executable/build` e `executable/dist` são gerados localmente e
não são versionados. Consulte [executable/README.md](executable/README.md) para
o fluxo de empacotamento.

Consulte [docs/architecture.md](docs/architecture.md) para as regras de
dependencia e a evolucao planejada.

## Ambiente

Requisitos:

- Python 3.12
- Poetry

```powershell
poetry install
poetry run translate-screen --help
poetry run python -m unittest discover -s tests
```

Pillow e pynput cuidam da captura e da hotkey. RapidOCR com ONNX Runtime realiza
o OCR localmente. O Google Cloud Translation v3 traduz somente o texto extraído,
usando credenciais externas ao repositório. Um cache em memória evita repetir
chamadas idênticas durante a mesma execução.
