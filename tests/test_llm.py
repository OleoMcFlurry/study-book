"""LLM 客户端测试。"""

import json

import httpx
import pytest

from knowledge_path_demo.llm import LlmCallOptions, LlmClient, LlmError, graph_from_llm_dict


def test_missing_key():
    client = LlmClient(api_key="")
    with pytest.raises(LlmError) as ei:
        client.ensure_configured()
    assert ei.value.code == "LLM_CONFIG_MISSING"


def test_chat_json_success(monkeypatch):
    captured: dict = {}

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "nodes": [
                                {"id": "a", "title": "A"},
                                {"id": "b", "title": "B"},
                                {"id": "c", "title": "C"},
                            ],
                            "edges": [{"from": "a", "to": "b"}],
                        }
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = LlmClient(api_key="sk-test", base_url="https://example.com/v1", model="my-model")
    original = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)
    data = client.chat_json(
        "sys",
        "user",
        options=LlmCallOptions(
            reasoning_effort="high",
            max_tokens=4096,
            enable_thinking=True,
            temperature=0.1,
        ),
    )
    assert len(data["nodes"]) == 3
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"]["model"] == "my-model"
    assert captured["body"]["reasoning_effort"] == "high"
    assert captured["body"]["max_tokens"] == 4096
    assert captured["body"]["max_completion_tokens"] == 4096
    assert captured["body"]["enable_thinking"] is True


def test_with_override():
    base = LlmClient(api_key="a", base_url="https://a/v1", model="m1")
    o = base.with_override(api_key="b", base_url="https://b/v1", model="m2")
    assert o.api_key == "b"
    assert o.base_url == "https://b/v1"
    assert o.model == "m2"
    assert base.api_key == "a"


def test_graph_from_llm_dict():
    g = graph_from_llm_dict(
        {
            "nodes": [{"id": "x", "title": "X"}],
            "edges": [],
        }
    )
    assert g.nodes[0].id == "x"
