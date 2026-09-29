from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from utils.models import model
from tools.lawyers import find_lawyers

SYSTEM_PROMPT = """
Eres un asistente legal útil. Tienes acceso a una base de datos de abogados.

Preguntale al usuario la descripción de su caso legal, la ciudad, el estado y la especialidad del abogado que necesita. 

Genera una descripcion del abaogado que el usuario necesita, incluyendo la ciudad, el estado y la especialidad.
Usa la tool `find_lawyers` para buscar abogados que coincidan con la descripción generada.

Una vez que el usuario seleccione un abogado, proporciónale sus datos de contacto y cualquier otra información relevante."""

agent = create_deep_agent(
    name="ampara-deep-agent",
    system_prompt=SYSTEM_PROMPT,
    model=model,
    backend=StateBackend(),
    tools=[find_lawyers],
    checkpointer=MemorySaver(),
)

# test agent
config = {"configurable": {"thread_id": "123abc"}}

while True:
    user_input = input("Usario: ")
    if user_input.lower() in ["exit", "quit"]:
        break

    agent_response = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]}, 
        config=config,
        version="v2",
        )

    # Check if execution was interrupted
    if agent_response.interrupts:

        # Extract interrupt information
        interrupt_value = agent_response.interrupts[0].value  
        action_requests = interrupt_value["action_requests"]
        review_configs = interrupt_value["review_configs"]

        # Create a lookup map from tool name to review config
        config_map = {cfg["action_name"]: cfg for cfg in review_configs}

        # Initialize an empty list to store decisions
        decisions = []

        # Display the pending actions to the user
        for action in action_requests:
            review_config = config_map[action["name"]]
            # print(f"Tool: {action['name']}")
            print(f"Descripcion: {action['description']}")
            available_lawyers = action['args']
            for idx, lawyer in enumerate(available_lawyers, start=1):
                print(f"{idx}: {lawyer['nombre']} - {lawyer['especialidades']} - {lawyer['ciudad']}, {lawyer['estado']}")

            # Prompt the user to select a lawyer from the list
            decision = input("Selecciona un abogado de la lista (proporciona el índice): ")

            # Append the user's decision to the decisions list
            decisions.append(
                {
                    "type": "respond",
                    "message": int(decision)  # Convert to integer
                }
            )

        agent_response = agent.invoke(Command(resume={"decisions": decisions}), config=config, version="v2")
        response = agent_response.value["messages"][-1].content

    else:
        response = agent_response.value["messages"][-1].content

    print(response)
