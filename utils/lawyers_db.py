import os
import json
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
        lawyer_specialties = lawyer.get("especialidades", [])
        lawyer_city = lawyer.get("ciudad")
        lawyer_state = lawyer.get("estado")
        lawyer_experience = lawyer.get("anios_experiencia")
        lawyer_license = lawyer.get("cedula_profesional")
        lawyer_description = lawyer.get("descripcion")
        if not lawyer_name or not lawyer_description:
            raise ValueError("Each lawyer must have 'nombre' and 'descripcion'.")

        lawyer_embedding = embeddings.embed_query(lawyer_description)
        rows.append((
            lawyer_name,
            lawyer_specialties,
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
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    especialidades TEXT[],
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
                    nombre, especialidades, ciudad, estado, anios_experiencia,
                    cedula_profesional, descripcion, embedding
                )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
            """, rows)


def search_lawyers(
    description: str,
    city: str | None = None,
    specialities: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Searches for lawyers based on the provided description, city, and speciality.
    Args:
        description (str): The description to search for.
        city (str, optional): The city to filter by. Defaults to None.
        speciality (str, optional): The speciality to filter by. Defaults to None.
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
        SELECT nombre, especialidades, ciudad, estado, anios_experiencia,
               cedula_profesional, descripcion,
               embedding <-> %s::vector AS distancia
        FROM abogados
    """
    conditions = []
    params = [query_vector]

    if city:
        conditions.append("ciudad = %s")
        params.append(city)

    if specialities:
        for speciality in specialities:
            conditions.append("%s = ANY(especialidades)")
            params.append(speciality)

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
        print(result)
        lawyer_name, specialties, city, state, experience, license_number, description, distance = result
        lawyers.append({
            "nombre": lawyer_name,
            "especialidades": specialties,
            "ciudad": city,
            "estado": state,
            "anios_experiencia": experience,
            "cedula_profesional": license_number,
            "descripcion": description,
            "distancia": distance,
        })

    return lawyers


if __name__ == "__main__":
    
    INGEST = False  # Set to True to ingest lawyers from the JSON file

    if INGEST:
        # Ingest lawyers from the JSON file into the vectorstore
        ingest_lawyers_from_json(json_path="data/lawyers.json")

    # Example search
    search_results = search_lawyers(description="juicios civiles, arrendamientos, herencias y amparos relacionados con derechos civiles. Ha asesorado a clientes en la redacción de contratos", limit=3)
    for result in search_results:   
        print(f"Lawyer: {result['nombre']}, Description: {result['descripcion']}, Distance: {result['distancia']}")
