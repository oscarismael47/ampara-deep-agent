import os
from pathlib import Path
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
model = init_chat_model(model="openai:gpt-4.1-mini")
