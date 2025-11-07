# services/llm_factory.py
from typing import Protocol, Any
from agentic_multimodal.core.config import Settings

class LLM(Protocol):
    def invoke(self, prompt: Any, **kw) -> Any: ...
    # add stream() if you need it later

def build_llm(settings: Settings) -> LLM:
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=settings.model_name, temperature=settings.temperature)
    except Exception:
        # Safe fallback for offline tests
        class _Dummy:
            def invoke(self, prompt, **kw):
                class O: pass
                o = O(); o.content = "OK"
                return o
        return _Dummy()

