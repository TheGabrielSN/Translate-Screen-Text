[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $PSScriptRoot "build"
$distRoot = Join-Path $PSScriptRoot "dist"
$specFile = Join-Path $PSScriptRoot "translate_screen_text.spec"
$executable = Join-Path $distRoot "TranslateScreenText\TranslateScreenText.exe"
$bundledModels = Join-Path $distRoot "TranslateScreenText\_internal\argos_models"

Push-Location $repositoryRoot
try {
    if (-not $SkipInstall) {
        poetry install --with dev --no-interaction
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências." }
    }

    poetry run python executable\prepare_argos_model.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar o modelo Argos." }

    $pyinstallerArguments = @(
        "--noconfirm",
        "--distpath", $distRoot,
        "--workpath", (Join-Path $buildRoot "pyinstaller")
    )
    if ($Clean) { $pyinstallerArguments += "--clean" }
    poetry run pyinstaller @pyinstallerArguments $specFile
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executável." }

    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "O executável esperado não foi gerado: $executable"
    }
    if (-not (Get-ChildItem -LiteralPath $bundledModels -Filter metadata.json -Recurse)) {
        throw "O modelo Argos não foi incluído na distribuição."
    }

    $verification = Start-Process `
        -FilePath $executable `
        -ArgumentList "--verify-bundled-argos" `
        -WindowStyle Hidden `
        -PassThru
    if (-not $verification.WaitForExit(120000)) {
        $verification.Kill()
        throw "A validação do modelo Argos excedeu o limite de 120 segundos."
    }
    if ($verification.ExitCode -ne 0) {
        throw "O executável não conseguiu traduzir com o modelo Argos incluído."
    }

    Write-Output "Build concluído: $executable"
}
finally {
    Pop-Location
}
