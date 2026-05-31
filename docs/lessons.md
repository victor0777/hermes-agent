# Lessons

## 2026-05-28 — qwen36-35b OpenAI-compatible 연결은 router endpoint를 사용한다

- 문제: Hermes에서 `qwen36-35b`를 OpenAI-compatible 방식으로 붙일 때 `http://192.168.0.199:30410` session-proxy를 `/v1/chat/completions` endpoint처럼 사용해 404가 발생했다.
- 원인: session-proxy는 Anthropic Messages 호환 경로에는 맞지만, Hermes `provider: custom`의 OpenAI-compatible chat completions endpoint가 아니었다. 또한 `REQ-20260528-003`는 로컬 193 collaboration instance에만 있던 drift 항목이고, authoritative `collaboration.ktl.com`에는 같은 advise가 `REQ-20260528-002`로 공지되어 있었다.
- 해결: authoritative router endpoint `http://192.168.0.199/v1`와 model alias `qwen36-35b`를 사용해 Hermes를 설정했다.
  ```yaml
  model:
    provider: custom
    default: qwen36-35b
    base_url: http://192.168.0.199/v1
    api_mode: chat_completions
  ```
  임시 HOME smoke test에서 일반 응답(`OPENAI_COMPAT_OK`)과 terminal tool call(`HERMES_TOOL_OK`) 모두 성공했다.
- 교훈: Hermes에서 OpenAI-compatible provider를 검증할 때는 session-proxy, LiteLLM/router, direct Pod/CNI IP를 구분해야 한다. 운영/일반 실험은 collaboration의 authoritative advise를 기준으로 stable router alias를 사용하고, direct CNI/Pod IP는 troubleshooting 용도로만 둔다.
