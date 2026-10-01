import os
import json
import unicodedata
from typing import Any
from pathlib import Path

import psycopg

from dotenv import load_dotenv
import yaml

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")


def _get_db_connection() -> psycopg.Connection[Any]:
    """Create a database connection for one operation."""
    missing_settings = [
        name
        for name, value in {
            "DB_NAME": DB_NAME,
            "DB_USER": DB_USER,
            "DB_PASSWORD": DB_PASSWORD,
            "DB_HOST": DB_HOST,
            "DB_PORT": DB_PORT,
        }.items()
        if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "Missing database environment variables: "
            + ", ".join(missing_settings)
        )

    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def ingest_legal_claims_by_lawyer(lawyer_id: str, subfolder: Path) -> None:
    """
    Ingests legal claims information for a specific lawyer into the PostgreSQL database.
    Args:
        lawyer_id (str): The ID of the lawyer for whom to ingest legal claims.
        subfolder (Path): The path to the subfolder containing the legal claims data.
    Returns:
        None
    """
    # Create table if it doesn't exist
    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS demandas (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    abogado_id UUID NOT NULL,
                    area_legal TEXT NOT NULL,
                    tipo_caso TEXT NOT NULL,
                    descripcion JSONB NOT NULL,
                    documentos JSONB NOT NULL,
                    informacion JSONB NOT NULL,
                    plantilla_demanda TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (abogado_id, area_legal, tipo_caso)
                )
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS demandas_abogado_area_tipo_idx
                ON demandas (abogado_id, area_legal, tipo_caso)
            """)

    # Iterate through all subfolders (legal areas) in the lawyer's folder.
    for legal_area_folder in subfolder.iterdir():
        if legal_area_folder.is_dir():
            legal_area = legal_area_folder.name

            # Iterate through all subfolders (case types) in the legal area folder.
            for case_type_folder in legal_area_folder.iterdir():
                if case_type_folder.is_dir():
                    case_type = case_type_folder.name

                    description_file = case_type_folder / "description.yaml"
                    documents_file = case_type_folder / "documents.yaml"
                    information_file = case_type_folder / "information.yaml"
                    claim_template_file = case_type_folder / "claim_template.md.j2"

                    required_files = (
                        description_file,
                        documents_file,
                        information_file,
                        claim_template_file,
                    )
                    missing_files = [
                        file.name for file in required_files if not file.is_file()
                    ]
                    if missing_files:
                        raise FileNotFoundError(
                            f"Missing files for {case_type_folder}: "
                            + ", ".join(missing_files)
                        )

                    with (
                        description_file.open(encoding="utf-8") as file,
                        documents_file.open(encoding="utf-8") as file_documents,
                        information_file.open(encoding="utf-8") as file_information,
                    ):
                        description_data = next(
                            document
                            for document in yaml.safe_load_all(file)
                            if document is not None
                        )
                        document_data = yaml.safe_load(file_documents)
                        information_data = yaml.safe_load(file_information)
                    claim_template = claim_template_file.read_text(encoding="utf-8")

                    # Upsert so re-running ingestion does not create duplicates.
                    with _get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                """
                                INSERT INTO demandas (
                                    abogado_id, area_legal, tipo_caso, descripcion,
                                    documentos, informacion, plantilla_demanda
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (abogado_id, area_legal, tipo_caso)
                                DO UPDATE SET
                                    descripcion = EXCLUDED.descripcion,
                                    documentos = EXCLUDED.documentos,
                                    informacion = EXCLUDED.informacion,
                                    plantilla_demanda = EXCLUDED.plantilla_demanda,
                                    updated_at = now()
                                """,
                                (
                                    lawyer_id,
                                    legal_area,
                                    case_type,
                                    json.dumps(description_data),
                                    json.dumps(document_data),
                                    json.dumps(information_data),
                                    claim_template,
                                ),
                            )


def ingest_legal_claims(legal_claims_folder_path: str) -> None:
    """
    Ingests legal claims information from a folder containing JSON files into the PostgreSQL database.
    Args:
        legal_claims_folder_path (str): Path to the folder containing JSON files with legal claims information.
    Returns:
        None
    """
    folder = Path(legal_claims_folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Legal claims folder does not exist: {folder}")

    for subfolder in folder.iterdir():
        if subfolder.is_dir():
            lawyer_name = subfolder.name
            # Conect to the abogados table and get the lawyer_id based on the lawyer_name
            with _get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM abogados WHERE nombre = %s", (lawyer_name,)
                    )
                    result = cursor.fetchone()
                    if result:
                        lawyer_id = result[0]
                        # Ingest legal claims for this lawyer
                        ingest_legal_claims_by_lawyer(lawyer_id, subfolder)
                    else:
                        print(f"No se encontró un abogado con el nombre: {lawyer_name}")


def _legal_claim_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a legal claim database row into a dictionary."""
    fields = (
        "id",
        "abogado_id",
        "area_legal",
        "tipo_caso",
        "descripcion",
        "documentos",
        "informacion",
        "plantilla_demanda",
        "created_at",
        "updated_at",
    )
    return dict(zip(fields, row))


def select_legal_claim(claim_id: str) -> dict[str, Any] | None:
    """Return one legal claim by its database ID, or None if it does not exist."""
    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                  SELECT id, abogado_id, area_legal, tipo_caso, descripcion,
                      documentos, informacion, plantilla_demanda, created_at, updated_at
                  FROM demandas
                WHERE id = %s
                """,
                (claim_id,),
            )
            row = cursor.fetchone()

    return _legal_claim_from_row(row) if row else None


def select_legal_claims(
    lawyer_id: str | None = None,
    legal_area: str | None = None,
    case_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return legal claims filtered by lawyer, legal area, and/or case type."""
    conditions = []
    parameters: list[str] = []

    if lawyer_id is not None:
        conditions.append("abogado_id = %s")
        parameters.append(lawyer_id)
    if legal_area is not None:
        conditions.append("area_legal = %s")
        parameters.append(legal_area)
    if case_type is not None:
        conditions.append("tipo_caso = %s")
        parameters.append(case_type)

    query = """
         SELECT id, abogado_id, area_legal, tipo_caso, descripcion,
             documentos, informacion, plantilla_demanda, created_at, updated_at
         FROM demandas
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY area_legal, tipo_caso"

    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

    return [_legal_claim_from_row(row) for row in rows]


def select_legal_claims_by_lawyer(lawyer_id: str) -> list[dict[str, Any]]:
    """Return legal claims filtered by lawyer ID."""
    legal_claims = select_legal_claims(lawyer_id=lawyer_id)
    # Select legal_area, case_type, and description from each legal claim
    return [
        {
            "area_legal": claim["area_legal"],
            "tipo_caso": claim["tipo_caso"],
            "descripcion": claim["descripcion"],
        }
        for claim in legal_claims
    ]

def update_legal_claim(
    claim_id: str,
    *,
    description: dict[str, Any] | None = None,
    documents: dict[str, Any] | None = None,
    information: dict[str, Any] | None = None,
    claim_template: str | None = None,
) -> bool:
    """Update supplied fields of a legal claim and return whether it existed."""
    updates = []
    parameters: list[Any] = []

    for column, value in (
        ("descripcion", description),
        ("documentos", documents),
        ("informacion", information),
    ):
        if value is not None:
            updates.append(f"{column} = %s")
            parameters.append(json.dumps(value))

    if claim_template is not None:
        updates.append("plantilla_demanda = %s")
        parameters.append(claim_template)

    if not updates:
        raise ValueError("At least one field must be supplied for update.")

    parameters.append(claim_id)
    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE demandas
                SET {', '.join(updates)}, updated_at = now()
                WHERE id = %s
                """,
                parameters,
            )
            return cursor.rowcount == 1


def remove_legal_claim(claim_id: str) -> bool:
    """Delete a legal claim by ID and return whether it existed."""
    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM demandas WHERE id = %s", (claim_id,))
            return cursor.rowcount == 1



def normalize_string(value: str) -> str:
    """
    Normalize a string by removing accents, converting to lowercase,
    and removing non-alphanumeric characters while preserving spaces.

    Args:
        value: The string to normalize.

    Returns:
        The normalized string.
    """
    normalized = unicodedata.normalize("NFKD", value)

    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
        and (char.isalnum() or char.isspace())
    ).lower()


if __name__ == "__main__":
    # Example usage
    INGEST = True  # Set to True to ingest legal claims from the folder

    if INGEST:
        # Ingest legal claims from the specified folder into the database
        ingest_legal_claims(legal_claims_folder_path=r"data\local\legal_claims")
