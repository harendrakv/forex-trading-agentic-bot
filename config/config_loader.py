import yaml
import os
from dotenv import load_dotenv

load_dotenv()  # Loads .env file

def load_config(path):
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    # Replace placeholders with environment variables
    cfg["models"]["groq"]["endpoint"] = os.getenv("GROQ_BASE_URL")
    cfg["models"]["groq"]["api_key"] = os.getenv("GROQ_API_KEY")
    cfg["models"]["openai"]["api_key"] = os.getenv("OPENAI_API_KEY")
    cfg['mt5_login']['login'] = int(os.getenv("MT5_LOGIN"))
    cfg['mt5_login']['password'] = os.getenv("MT5_PASSWORD")
    cfg['mt5_login']['server'] = os.getenv("MT5_SERVER")
    return cfg

cfg = load_config("config/settings.yaml")
