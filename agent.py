from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from utils.models import model
from tools.lawyers import find_lawyers, select_lawyer

SYSTEM_PROMPT = """
Eres un asistente legal útil. Tienes acceso a una base de datos de abogados.

Preguntale al usuario la descripción de su caso legal, la ciudad, el estado y la especialidad del abogado que necesita. 

Genera una descripcion del abaogado que el usuario necesita, incluyendo la ciudad, el estado y la especialidad.
Usa la tool `find_lawyers` para buscar abogados que coincidan con la descripción generada.
Y a continuacion usa la tool `select_lawyer` para seleccionar un abogado de la lista y obtener sus datos de contacto y otra información relevante.

Una vez que el usuario seleccione un abogado, proporciónale sus datos de contacto y cualquier otra información relevante."""

agent = create_deep_agent(
    name="ampara-deep-agent",
    system_prompt=SYSTEM_PROMPT,
    model=model,
    backend=StateBackend(),
    tools=[find_lawyers, select_lawyer],
    interrupt_on={
        "select_lawyer": {
            "allowed_decisions": ["edit"]
        }
    },
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

    if agent_response.interrupts:
        interrupt = agent_response.interrupts[0].value
        interrupt_type = interrupt.get("type")
        interrupt_message = interrupt.get("message")
        interrupt_required_field = interrupt.get("required_field")
        lawyers_dict = interrupt.get("options", [])
        print(interrupt_message)
        for lawyer_name, lawyer_data in lawyers_dict.items():
            print(f"- {lawyer_name}: {lawyer_data['descripcion']}")
        user_selection = input("Usuario: ")
        agent_response = agent.invoke(Command(resume={interrupt_required_field: user_selection}), config=config, version="v2")
        response = agent_response.value["messages"][-1].content

    else:
        response = agent_response.value["messages"][-1].content

    print(response)
