"""Load explicitly supported ignored project settings without logging secrets."""
import os
from pathlib import Path

def load_project_environment():
    target=Path(__file__).resolve().parents[2]/'.env.local'
    if not target.is_file():
        return
    allowed={'DATABASE_URL','OPENAI_API_KEY','OPENAI_MODEL','OPENAI_VERIFY_MODEL','OPENAI_CLASSIFY_MODEL','OPENAI_REASONING_EFFORT'}
    for line in target.read_text(encoding='utf-8-sig').splitlines():
        if not line.lstrip().startswith('#') and '=' in line:
            name,value=line.split('=',1)
            if name.strip() in allowed:
                os.environ.setdefault(name.strip(),value.strip().strip('"').strip("'"))
