"""Provider-neutral LLM layer (ADR 0001 D4).

All model access goes through the LLMProvider protocol. The mock provider is
the default everywhere (demo mode, tests, CI); Anthropic is the first real
implementation. No module outside this package may import a vendor SDK.
"""
