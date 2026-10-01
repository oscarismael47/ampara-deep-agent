import os
import json
import unicodedata
from typing import Any

import psycopg
from langchain_openai import OpenAIEmbeddings

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def _to_pgvector(values: list[float]) -> str:
    """Serialize an embedding in the text format accepted by pgvector."""
    return "[" + ",".join(str(value) for value in values) + "]"


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


def ingest_lawyers_from_json(json_path: str) -> None:
    """
    Ingests lawyers' information from a JSON file into the PostgreSQL database.
    Args:
        json_path (str): Path to the JSON file containing lawyers' information.
    Returns:
        None
    """

    with open(json_path, "r", encoding="utf-8") as f:
        lawyers = json.load(f)

    rows = []
    for lawyer in lawyers:
        lawyer_name = lawyer.get("nombre")
        areas_legales = lawyer.get("areas_legales", [])
        tipo_casos = lawyer.get("tipo_casos", [])
        lawyer_city = lawyer.get("ciudad")
        lawyer_state = lawyer.get("estado")
        lawyer_experience = lawyer.get("anios_experiencia")
        lawyer_license = lawyer.get("cedula_profesional")
        lawyer_description = lawyer.get("descripcion")
        
        if not lawyer_name or not lawyer_description:
            raise ValueError("Each lawyer must have 'nombre' and 'descripcion'.")

        # Remove accents and convert to lowercase for consistent searching
        lawyer_city = normalize_string(lawyer_city) if lawyer_city else None
        lawyer_state = normalize_string(lawyer_state) if lawyer_state else None
        areas_legales = [normalize_string(s) for s in areas_legales] if areas_legales else []
        tipo_casos = [normalize_string(s) for s in tipo_casos] if tipo_casos else []

        # Generate embedding for the lawyer's description
        lawyer_embedding = embeddings.embed_query(lawyer_description)

        # Prepare the row for insertion into the database
        rows.append((
            lawyer_name,
            areas_legales,
            tipo_casos,
            lawyer_city,
            lawyer_state,
            lawyer_experience,
            lawyer_license,
            lawyer_description,
            _to_pgvector(lawyer_embedding),
        ))

    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS abogados (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    nombre TEXT NOT NULL,
                    areas_legales TEXT[],
                    tipo_casos TEXT[],
                    ciudad TEXT,
                    estado TEXT,
                    anios_experiencia INT,
                    cedula_profesional TEXT,
                    descripcion TEXT,
                    embedding VECTOR(1536)
                );
            """)
            cursor.executemany("""
                INSERT INTO abogados (
                    nombre, areas_legales, tipo_casos, ciudad, estado, anios_experiencia,
                    cedula_profesional, descripcion, embedding
                )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """, rows)


def get_lawyer_table_info() -> dict[str, Any]:
    """
    Retrieves table description information for the 'abogados' table in the PostgreSQL database.
    Retrieves first 3 rows as example data.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing lawyers' information.
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'abogados';
            """)
            columns_info = cursor.fetchall()

            cursor.execute("SELECT * FROM abogados LIMIT 3;")
            example_rows = cursor.fetchall()

    # Convert the results into a list of dictionaries for easier consumption
    column_names = [col[0] for col in columns_info]
    example_data = [dict(zip(column_names, row)) for row in example_rows]

    return {"columns_info": columns_info, "example_data": example_data}


def search_lawyers(
    description: str,
    city: str | None = None,
    state: str | None = None,
    legal_areas: list[str] | None = None,
    case_types: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Searches for lawyers based on the provided description, city, state, and speciality.
    Args:
        description (str): The description to search for.
        city (str, optional): The city to filter by. Defaults to None.
        state (str, optional): The state to filter by. Defaults to None.
        legal_areas (list[str], optional): The legal areas to filter by. Defaults to None.
        case_types (list[str], optional): The types of cases to filter by. Defaults to None.
        limit (int, optional): The maximum number of results to return. Defaults to 3.
    Returns:
        list: A list of lawyers matching the search criteria.
    """
    if not description.strip():
        raise ValueError("description cannot be empty.")
    if limit < 1:
        raise ValueError("limit must be greater than zero.")

    query_embedding = embeddings.embed_query(description)
    query_vector = _to_pgvector(query_embedding)

    sql_query = """
        SELECT id, nombre, areas_legales, tipo_casos, ciudad, estado, anios_experiencia,
               cedula_profesional, descripcion,
               embedding <-> %s::vector AS distancia
        FROM abogados
    """
    conditions = []
    params = [query_vector]

    if city:
        city = normalize_string(city)
        conditions.append("ciudad = %s")
        params.append(city)

    if state:
        state = normalize_string(state)
        conditions.append("estado = %s")
        params.append(state)

    if legal_areas:
        for area in legal_areas:
            area = normalize_string(area)
            conditions.append("%s = ANY(areas_legales)")
            params.append(area)

    if case_types:
        for caso in case_types:
            caso = normalize_string(caso)
            conditions.append("%s = ANY(tipo_casos)")
            params.append(caso)

    if conditions:
        sql_query += " WHERE " + " AND ".join(conditions)

    sql_query += " ORDER BY distancia ASC LIMIT %s"
    params.append(limit)

    with _get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_query, params)
            search_results = cursor.fetchall()

    lawyers = []
    for result in search_results:
        lawyer_id, lawyer_name, legal_areas, case_types, city, state, experience, license_number, description, distance = result
        lawyers.append({
            "id": lawyer_id,
            "nombre": lawyer_name,
            "areas_legales": legal_areas,
            "tipo_casos": case_types,
            "ciudad": city,
            "estado": state,
            "anios_experiencia": experience,
            "cedula_profesional": license_number,
            "descripcion": description,
            "distancia": distance,
        })

    return lawyers


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
    INGEST = False  # Set to True to ingest lawyers from the JSON file

    if INGEST:
        # Ingest lawyers from the JSON file into the vectorstore
        ingest_lawyers_from_json(json_path="data/lawyers.json")

    # Example table info
    table_info = get_lawyer_table_info()
    print(f"Table Info: {table_info}")

    # Example search
    search_results = search_lawyers(description="juicios civiles, arrendamientos, herencias y amparos relacionados con derechos civiles. Ha asesorado a clientes en la redacción de contratos", limit=3)
    for result in search_results:   
        print(f"Lawyer: {result['nombre']}, Description: {result['descripcion']}, Distance: {result['distancia']}, City: {result['ciudad']}, State: {result['estado']}")

