import os
import psycopg
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

# Initialize the OpenAI embeddings model. You can change the model to any other available embedding model if needed.
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Set up the PostgreSQL connection string. Replace with your actual database credentials.
CONEXION = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Initialize the PGVector vectorstore with the embeddings and connection string.
# It creates two tables in the database: langchain_pg_collection and langchain_pg_embedding. 
# The collection name is set to "abogados". 
vectorstore = PGVector(
    embeddings=embeddings,
    collection_name="abogados",
    connection=CONEXION,
    use_jsonb=True,  # permite guardar metadata como JSON
)

def add_lawyer(lawyer: dict) -> None:
    """
    Adds a lawyer's information to the vectorstore.
    Args:
        lawyer (dict): A dictionary containing lawyer's information.
    Returns:
        None
    """
    document = Document(
        page_content=lawyer["descripcion"],
        metadata={
            "nombre": lawyer["nombre"],
            "especialidades": lawyer["especialidades"],
            "ciudad": lawyer["ciudad"],
            "estado": lawyer["estado"],
            "anios_experiencia": lawyer["anios_experiencia"],
            "cedula_profesional": lawyer["cedula_profesional"],
        },
    )
    vectorstore.add_documents([document])


def search_lawyers( query: str,
                     city: str = None, speciality: str = None,
                     limit: int = 3) -> list[Document]:
    """
    Searches for lawyers in the vectorstore based on the query, city, and speciality.
    Args:
        query (str): The search query.
        city (str, optional): The city to filter by. Defaults to None.
        speciality (str, optional): The speciality to filter by. Defaults to None.
        limit (int, optional): The maximum number of results to return. Defaults to 3.
    Returns:
        list[Document]: A list of documents representing the search results.
    """
    filter = {}

    if city:
        filter["ciudad"] = city

    if speciality:
        filter["especialidades"] = {"$in": [speciality]}

    results = vectorstore.similarity_search_with_score(
        query,
        k=limit,
        filter=filter if filter else None,
    )

    # sort results by score in descending order
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def lawyer_exists(lawyer_name: str) -> bool:
    """
    Checks if a lawyer with the given name already exists in the database.
    Args:
        lawyer_name (str): The name of the lawyer to check.
    Returns:
        bool: True if the lawyer exists, False otherwise.
    """
    conn = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

    # Check if 'abogados' table exists
    with conn.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'langchain_pg_collection')")
        table_exists = cursor.fetchone()[0]
        if not table_exists:
            conn.close()
            return False

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM langchain_pg_embedding WHERE cmetadata->>'nombre' = %s", (lawyer_name,))
        rows = cursor.fetchall()
        for row in rows:
            if row[4].get("nombre") == lawyer_name:
                conn.close()
                return True
        conn.close()
        return False


def ingest_lawyers_from_json(json_path: str) -> None:
    """
    Ingests lawyers' information from a JSON file into the vectorstore.
    Args:
        json_path (str): The path to the JSON file containing lawyers' information.
    Returns:
        None
    """
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        lawyers = json.load(f)

    for lawyer in lawyers:
        lawyer_name = lawyer.get("nombre")
        existing_lawyer = lawyer_exists(lawyer_name)

        if not existing_lawyer:
            add_lawyer(lawyer)


if __name__ == "__main__":
    # Ingest lawyers from the JSON file into the vectorstore
    ingest_lawyers_from_json(json_path="data/lawyers.json")
    query = "juicios civiles, arrendamientos, herencias y amparos relacionados"
    results = search_lawyers(query=query)
    for result, score in results:
        print(f"Score: {score}, Lawyer: {result.metadata['nombre']}, Description: {result.page_content}")