from pydantic import BaseModel
from deepagents.graph import DeepAgentState

class MainAgentState(DeepAgentState):
    """
    This class represents the state of the main agent. 
    It extends the DeepAgentState class and can be used to 
    store any additional state information specific to the main agent.
    """
    selected_lawyer: dict | None = None

class Decision(BaseModel):
    """
    This class represents a decision made by the user when selecting a lawyer from the list of available lawyers.
    It contains the name of the lawyer selected by the user.
    """
    lawyer_name: dict