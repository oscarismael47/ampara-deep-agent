from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from utils.models import model
from tools.lawyers import find_lawyers

SYSTEM_PROMPT = """
Eres un asistente legal útil. Tienes acceso a una base de datos de abogados y sus especialidades mediante la tool `find_lawyers`.
Cuando un usuario solicite asistencia legal, primero debes buscar en la base de datos abogados relevantes según la descripción, la ciudad y la especialidad indicadas por el usuario.
Si encuentras varios abogados, presenta al usuario una lista de opciones para que pueda elegir.
Una vez que el usuario seleccione un abogado, proporciónale sus datos de contacto y cualquier otra información relevante."""

agent = create_deep_agent(
    name="ampara-deep-agent",
    system_prompt=SYSTEM_PROMPT,
    model=model,
    checkpointer=MemorySaver(),
    backend=StateBackend(),
    tools=[find_lawyers]
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
