# Empacotamento Windows

Esta pasta concentra tudo que pertence à criação e à distribuição do
executável. O código da aplicação permanece exclusivamente em `../src`.

## Conteúdo versionado

- `build_windows.ps1`: instala dependências, prepara o modelo, executa o
  PyInstaller e valida uma tradução real no binário gerado.
- `prepare_argos_model.py`: copia ou baixa o modelo Argos `en -> pt-BR`.
- `translate_screen_text.spec`: define módulos, recursos, ícone e formato
  `onedir`.
- `assets/icon.ico`: ícone nativo incorporado ao arquivo `.exe`.

## Conteúdo gerado

- `build/argos_models`: modelo preparado para inclusão.
- `build/pyinstaller`: cache e arquivos intermediários do PyInstaller.
- `dist/TranslateScreenText`: pasta autocontida que deve ser distribuída.

Para gerar a aplicação a partir da raiz do repositório:

```powershell
.\executable\build_windows.ps1
```

Use `-SkipInstall` para não repetir `poetry install` e `-Clean` para descartar o
cache de análise do PyInstaller.
