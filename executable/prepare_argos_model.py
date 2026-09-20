"""Baixa e prepara o modelo Argos en -> pt-BR para o build."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

SOURCE_LANGUAGE = "en"
ARGOS_TARGET_LANGUAGE = "pb"
EXECUTABLE_ROOT = Path(__file__).resolve().parent
OUTPUT_DIRECTORY = EXECUTABLE_ROOT / "build" / "argos_models"


def prepare_model() -> Path:
    output_directory = OUTPUT_DIRECTORY.resolve()
    expected_directory = (EXECUTABLE_ROOT / "build" / "argos_models").resolve()
    if output_directory != expected_directory:
        raise RuntimeError("Diretório de modelos do build fora do local esperado.")

    if output_directory.exists():
        shutil.rmtree(output_directory)
    output_directory.mkdir(parents=True)

    import argostranslate.package as package_module
    import argostranslate.settings as settings

    installed_package = next(
        (
            candidate
            for candidate in package_module.get_installed_packages()
            if candidate.from_code == SOURCE_LANGUAGE
            and candidate.to_code == ARGOS_TARGET_LANGUAGE
        ),
        None,
    )
    if installed_package is not None:
        destination = output_directory / installed_package.package_path.name
        print(f"Copiando modelo Argos já instalado: {installed_package.package_path}")
        shutil.copytree(installed_package.package_path, destination)
        return _validate_prepared_model(output_directory)

    print("Atualizando o índice de modelos do Argos...")
    package_module.update_package_index()
    if not settings.local_package_index.is_file():
        raise RuntimeError(
            "Não foi possível obter o índice de modelos do Argos. "
            "Verifique a conexão com a internet."
        )

    package = next(
        (
            candidate
            for candidate in package_module.get_available_packages()
            if candidate.from_code == SOURCE_LANGUAGE
            and candidate.to_code == ARGOS_TARGET_LANGUAGE
            and candidate.type == "translate"
        ),
        None,
    )
    if package is None:
        raise RuntimeError("Modelo Argos en -> pb não encontrado no índice remoto.")

    print("Baixando e preparando o modelo Argos en -> pt-BR...")
    archive_path = package.download()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = (output_directory / member.filename).resolve()
            if not destination.is_relative_to(output_directory):
                raise RuntimeError("O pacote Argos contém um caminho inseguro.")
        archive.extractall(output_directory)
    return _validate_prepared_model(output_directory)


def _validate_prepared_model(output_directory: Path) -> Path:
    for metadata_path in output_directory.glob("*/metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("from_code") == SOURCE_LANGUAGE
            and metadata.get("to_code") == ARGOS_TARGET_LANGUAGE
        ):
            installed_model = metadata_path.parent
            print(f"Modelo preparado em: {installed_model}")
            return installed_model

    raise RuntimeError("O modelo Argos foi preparado, mas não pôde ser validado.")


if __name__ == "__main__":
    prepare_model()
