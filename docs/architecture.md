# Arquitetura

## Objetivo desta fase

Validar a captura manual e preparar o caminho mais simples do produto:

```text
F6 -> seleção da área -> captura PNG -> OCR -> tradução
   -> blur das regiões originais -> overlay transparente -> exclusão do PNG
```

Captura contínua e detecção de mudança permanecem como evoluções futuras.

## Componentes

- `models.py`: dados que atravessam o pipeline, sem dependencia de bibliotecas
  externas.
- `contracts.py`: interfaces que os adaptadores precisam implementar.
- `config.py`: opcoes do caso de uso, como idiomas e confianca minima do OCR.
- `pipeline.py`: coordena as etapas; nao conhece bibliotecas concretas.
- `capture.py`: coordena captura e armazenamento sem depender de Pillow.
- `capture_ui.py`: mantém Tkinter no thread principal e recebe hotkeys por fila.
- `adapters/tk_translation_overlay.py`: desfoca cada região original e exibe
  o texto traduzido em uma janela transparente sobre a tela.
- `adapters/input_activity.py`: monitora teclado, cliques do mouse e controles
  XInput para remover o overlay assim que o usuário voltar a interagir.
- `adapters/rapidocr_provider.py`: converte a resposta do RapidOCR nos modelos
  `TextRegion` do domínio.
- `adapters/google_translation.py`: integra o contrato `TranslationProvider` à
  API Google Cloud Translation v3 usando ADC.
- `translation.py`: mantém o cache de traduções da execução atual.
- `adapters/`: integracoes com OCR, traducao e renderizacao.
- `cli.py`: ponto de entrada e futuro local de composicao das implementacoes.

## Regra de dependencias

```text
CLI/adaptadores ---> pipeline ---> contratos/modelos
                          |-----> configuracao
```

O nucleo nunca deve importar um adaptador. Essa direcao permite trocar, por
exemplo, o motor de OCR sem alterar o pipeline.

## Modelo de execucao

1. O OCR recebe um `Frame` e devolve `TextRegion` com texto, posicao e confianca.
2. O pipeline ignora regioes abaixo da confianca configurada.
3. O tradutor recebe apenas regioes elegiveis.
4. O renderer recebe o frame original e as regioes traduzidas.
5. O resultado preserva tanto as regioes reconhecidas quanto as traduzidas para
   diagnostico e testes.

## Evolucao planejada

Os proximos adaptadores devem ser adicionados conforme forem implementados:

1. Captura manual de uma região do monitor principal. **Implementado.**
2. Motor de OCR e impressão do texto reconhecido. **Implementado.**
3. Provedor Google Cloud Translation e cache em memória. **Implementado.**
4. Overlay transparente com blur por região. **Implementado.**
5. Captura de uma janela específica e múltiplos monitores.
6. Detecção de mudança entre frames.

Quando o processamento em tempo real for introduzido, cada frame devera possuir
um identificador. Resultados atrasados serao descartados para que uma traducao
antiga nao seja desenhada sobre uma nova cena.
