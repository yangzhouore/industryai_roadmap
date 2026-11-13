"""Bounded OpenAI Responses HTTP adapter. No credentials are logged or persisted."""
from dataclasses import dataclass
import json
import os
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

ENDPOINT = "https://api.openai.com/v1/responses"
MAX_RESPONSE_BYTES = 2_000_000


class ProviderError(RuntimeError):
    pass


class MissingCredentials(ProviderError):
    pass


@dataclass(frozen=True)
class StructuredResult:
    data: dict
    response_id: str
    model: str
    usage: dict | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAIProvider:
    """Three bounded requests per edition; injected transport is only for adapter tests."""
    def __init__(self, api_key=None, model=None, verification_model=None, *, classification_model=None,
                 reasoning_effort=None, timeout=45, retries=1, max_output_tokens=12000,
                 transport=None, sleep=time.sleep, before_request=None, after_response=None):
        # Callers decide when to load project credentials; tests stay environment-isolated.
        key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise MissingCredentials("OPENAI_API_KEY is missing; real editorial generation is blocked")
        self._api_key = key.strip()
        self.model = model or os.getenv("OPENAI_MODEL", "") or "gpt-6.1-terra"
        self.classification_model = classification_model or os.getenv("OPENAI_CLASSIFY_MODEL", "") or "gpt-6-luna"
        self.verification_model = verification_model or os.getenv("OPENAI_VERIFY_MODEL", "") or "gpt-6.1-terra"
        self.reasoning_effort = reasoning_effort or os.getenv("OPENAI_REASONING_EFFORT", "") or "low"
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ProviderError("Requested models support none/low/medium/high/xhigh/max reasoning, not minimal")
        if not self.model or any(c.isspace() for c in self.model + self.verification_model + self.classification_model):
            raise ProviderError("Configure OPENAI_MODEL with a Structured Outputs-capable model")
        if not 1 <= timeout <= 120 or not 0 <= retries <= 2 or not 1024 <= max_output_tokens <= 16000:
            raise ValueError("Provider limits exceed permitted request budget")
        self.timeout, self.retries, self.max_output_tokens = timeout, retries, max_output_tokens
        self._transport, self._sleep = transport, sleep
        self.before_request, self.after_response = before_request, after_response
        self.usage = []

    def _before(self, request, attempt):
        if self.before_request is not None:
            self.before_request({"stage": request["text"]["format"]["name"].removeprefix("industrial_"),
                "model": request["model"], "maxOutputTokens": request["max_output_tokens"],
                "attempt": attempt, "request": request})

    def _post(self, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(body) > 250_000:
            raise ProviderError("Editorial request exceeds input budget")
        request = Request(ENDPOINT, data=body, method="POST", headers={
            "Authorization": "Bearer " + self._api_key, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "IndustrialAIDigest/0.2"})
        opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
        for attempt in range(self.retries + 1):
            # Budget reservation must happen before EACH network attempt, including retries.
            self._before(payload, attempt)
            try:
                with opener.open(request, timeout=self.timeout) as response:
                    if response.status != 200:
                        raise ProviderError("Unexpected OpenAI HTTP status")
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ProviderError("OpenAI response exceeds size limit")
                    try:
                        return json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise ProviderError("OpenAI returned invalid JSON") from None
            except HTTPError as error:
                status = error.code
                # Never expose response bodies: they can echo prompts or credentials.
                error.close()
                if status in {429, 500, 502, 503, 504} and attempt < self.retries:
                    self._sleep(min(2 ** attempt, 4))
                    continue
                if status in {401, 403}:
                    raise ProviderError(f"OpenAI authentication/project access failed (HTTP {status})") from None
                raise ProviderError(f"OpenAI request failed (HTTP {status})") from None
            except (URLError, TimeoutError, OSError):
                if attempt < self.retries:
                    self._sleep(min(2 ** attempt, 4))
                    continue
                raise ProviderError("OpenAI network request failed or timed out") from None
        raise ProviderError("OpenAI request exhausted its bounded retry budget")

    def complete_json(self, stage, schema, payload, instructions):
        if stage not in {"classify", "generate", "verify"}:
            raise ValueError("Unknown editorial request stage")
        model = {"classify": self.classification_model, "generate": self.model, "verify": self.verification_model}[stage]
        request = {"model": model, "store": False, "max_output_tokens": self.max_output_tokens,
                   "instructions": instructions,
                   "input": [{"role": "user", "content": [{"type": "input_text",
                              "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]}],
                   "text": {"format": {"type": "json_schema", "name": "industrial_" + stage,
                                        "strict": True, "schema": schema}}}
        if model.startswith(("gpt-6-", "gpt-6.1-")):
            request["reasoning"] = {"effort": self.reasoning_effort}
        if self._transport:
            self._before(request, 0)
            response = self._transport(request)
        else:
            response = self._post(request)
        if isinstance(response, dict):
            usage = response.get("usage") if isinstance(response.get("usage"), dict) else None
            details = (usage or {}).get("output_tokens_details") or {}
            record = {"stage": stage, "model": response.get("model", model), "requestedModel": model,
                      "responseId": response.get("id"), "status": response.get("status"), "usage": usage,
                      "reasoningTokens": details.get("reasoning_tokens") if isinstance(details, dict) else None}
            self.usage.append(record)
            if self.after_response is not None:
                self.after_response(record)
        if not isinstance(response, dict) or response.get("status") != "completed" or response.get("error"):
            raise ProviderError("OpenAI response was incomplete or failed")
        response_id = response.get("id")
        if not isinstance(response_id, str) or not response_id.startswith("resp_"):
            raise ProviderError("OpenAI response missing auditable response ID")
        texts = []
        for item in response.get("output", []):
            if not isinstance(item, dict):
                raise ProviderError("Malformed OpenAI output")
            if item.get("type") == "reasoning":
                continue
            if item.get("type") != "message" or item.get("role") != "assistant":
                raise ProviderError("Unexpected OpenAI output type")
            for part in item.get("content", []):
                if part.get("type") == "refusal":
                    raise ProviderError("OpenAI refused the editorial request")
                if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                    raise ProviderError("Unexpected OpenAI message content")
                texts.append(part["text"])
        if len(texts) != 1:
            raise ProviderError("OpenAI response must contain one structured output")
        try:
            data = json.loads(texts[0])
        except ValueError:
            raise ProviderError("OpenAI structured output was invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderError("OpenAI structured output must be an object")
        return StructuredResult(data, response_id, response.get("model", model), response.get("usage"))
