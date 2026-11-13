"""Small JSON-safe redaction boundary for operational reports."""
import os
import re


def redacted(value):
    if isinstance(value, dict):
        return {str(k): redacted(v) for k, v in value.items()
                if str(k).lower() not in {'api_key', 'apikey', 'authorization', 'openai_api_key'}}
    if isinstance(value, (list, tuple)):
        return [redacted(v) for v in value]
    if isinstance(value, str):
        for name in ('OPENAI_API_KEY', 'DATABASE_URL'):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, '[redacted]')
        value = re.sub(r'sk-(?:proj-|svcacct-)?[\w-]{8,}', '[redacted]', value)
        value = re.sub(r'(?:postgres(?:ql)?|https?)://[^\s/@]+:[^\s/@]+@',
                       '[redacted credentials]@', value)
    return value
