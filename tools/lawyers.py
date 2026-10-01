from pydantic import BaseModel
from langchain_core.tools import tool
from langgraph.types import interrupt
from typing import Any

from utils.lawyers_db import search_lawyers, get_lawyer_table_info as get_lawyer_table_info_from_db


@tool
def get_lawyer_table_info():
    """Return the columns and sample rows from the lawyers database table."""
    return get_lawyer_table_info_from_db()


class Decision(BaseModel):
    approved: bool
    note: str | None = None


@tool
def find_lawyers(lawyer_description_to_search: str, city: str | None = None, specialities: list[str] | None = None, limit: int = 3) -> dict[str, Any] | str:
    """
    Finds lawyers based on the provided description, city, and specialities. An interrupt is created to allow the user to select a lawyer from the list of results.
    Args:
        lawyer_description_to_search (str): The lawyer description to search for.
        city (str, optional): The city to filter by. Defaults to None.
        specialities (list[str], optional): The specialities to filter by. Defaults to None.
        limit (int, optional): The maximum number of results to return. Defaults to 3.
    Returns:
        dict[str, any] | str: A dictionary containing the selected lawyer's data or a string indicating no lawyers were found.

    Example: 
        lawyer_description_to_search = "Abogado especializado en derecho laboral con experiencia en litigios."
        city = "Ciudad de México"
        specialities = ["laboral"]

    """
    # Search for lawyers using the search_lawyers function
    retrieved_lawyers = search_lawyers(description=lawyer_description_to_search, city=city, legal_areas=specialities, limit=limit)

    # Copy the list of lawyers to avoid modifying the original list
    lawyers = list(retrieved_lawyers)

    # Delete the 'distancia' and 'id' field from each lawyer dictionary in the list

    for lawyer in lawyers:
        del lawyer["distancia"]  
        del lawyer["id"]

    # If no lawyers are found, return a message indicating that
    if not lawyers:
        return "No se encontraron abogados que coincidan con la descripción proporcionada."

    # Create an interruption value to prompt the user to select a lawyer from the list
    interruption_value = {
        "action_requests":
            [
                {
                        "name": "find_lawyers",
                        "args": lawyers,
                        "description": "Encontré los siguientes abogados y selecciona uno"
                }
                ],
                "review_configs": [
                    {
                        "action_name":"find_lawyers",
                        "allowed_decisions": ["respond"]
                    }
                ]
            }   
    
    # Create an interrupt with the interruption value and a response schema
    decisions = interrupt(value=interruption_value,
                          response_schema={
                              "decisions": [
                                  {
                                      "type": "respond",
                                      "message": "Integer representing the index of the selected lawyer from the list."
                                    }
                                ]
                            }
                        )

    # Extract the user's decision from the interrupt
    decisions = decisions.get("decisions", [])
    lawyers_index = int(decisions[0]["message"]) - 1  # Convert to integer, and adjust for 1-based indexing

    # Return the selected lawyer's data based on the user's answer
    return retrieved_lawyers[lawyers_index]