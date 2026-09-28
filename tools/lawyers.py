from typing import Any
from langchain_core.tools import tool
from langgraph.types import Command, interrupt

from utils.lawyers_db import search_lawyers

@tool
def find_lawyers(lawyer_description_to_search: str, city: str | None = None, specialities: list[str] | None = None, limit: int = 3) -> list[dict[str, any]]:
    """
    Finds lawyers based on the provided description, city, and speciality.
    Args:
        lawyer_description_to_search (str): The lawyer description to search for.
        city (str, optional): The city to filter by. Defaults to None.
        specialities (list[str], optional): The specialities to filter by. Defaults to None.
        limit (int, optional): The maximum number of results to return. Defaults to 3.
    Returns:
        list: A list of lawyers matching the search criteria.

    Example: 
        lawyer_description_to_search = "Abogado especializado en derecho laboral con experiencia en litigios."
        city = "Ciudad de México"
        specialities = ["laboral"]

    """
    lawyers = search_lawyers(description=lawyer_description_to_search, city=city, specialities=specialities, limit=limit)

    if not lawyers:
        return "No se encontraron abogados que coincidan con la descripción proporcionada."

    lawyers_dict = {lawyer["nombre"]: lawyer for lawyer in lawyers}
    
    selected_lawyer_name = interrupt(
        {
            "interrupt_name": "find_lawyers",
            "type": "select",
            "message": "Selecciona un abogado de la lista:",
            "options": lawyers_dict,
            "required_field": "lawyer_name"
        }
    )
    
    return lawyers_dict[selected_lawyer_name["lawyer_name"]]