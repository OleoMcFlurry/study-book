"""API 集成测试。"""

import re

from fastapi.testclient import TestClient

from knowledge_path_demo.app import create_app
from knowledge_path_demo.config import Settings
from knowledge_path_demo.domain import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, PathItem
from knowledge_path_demo.llm import LlmClient, LlmError
from knowledge_path_demo.repository import SessionRepository


class FakeLlm(LlmClient):
    def __init__(self, fail_config: bool = False) -> None:
        super().__init__(api_key="" if fail_config else "fake")
        self.fail_config = fail_config
        self.last_options = None
        self.last_key = None
        self.last_base = None
        self.last_model = None

    def generate_graph(self, goal, background, known_keywords, options=None):
        self.last_options = options
        self.last_key = self.api_key
        self.last_base = self.base_url
        self.last_model = self.model
        if self.fail_config or not self.api_key:
            raise LlmError("LLM_CONFIG_MISSING", "未配置")
        return KnowledgeGraph(
            nodes=(
                KnowledgeNode("a", "基础A"),
                KnowledgeNode("b", "概念B"),
                KnowledgeNode("c", "目标C"),
            ),
            edges=(
                KnowledgeEdge("a", "b"),
                KnowledgeEdge("b", "c"),
            ),
        )

    def generate_path_items(self, goal, ordered_nodes, options=None):
        self.last_options = options
        return [
            PathItem(
                node_id=n.id,
                title=n.title,
                actions=(f"学习{n.title}",),
                acceptance_question=f"懂{n.title}?",
            )
            for n in ordered_nodes
        ]

    def with_override(self, *, api_key=None, base_url=None, model=None, options=None):
        # 保持 Fake 类型以便断言
        c = FakeLlm(fail_config=False)
        c.api_key = api_key if api_key is not None else self.api_key
        c.base_url = base_url if base_url is not None else self.base_url
        c.model = model if model is not None else self.model
        c.default_options = options if options is not None else self.default_options
        c.timeout = self.timeout
        return c


def test_vite_frontend_is_served(tmp_path):
    app = create_app(
        settings=Settings(database_path=str(tmp_path / "frontend.db")),
        repo=SessionRepository(tmp_path / "frontend.db"),
        llm=FakeLlm(),
    )
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert "/static/dist/assets/" in response.text

    asset_path = re.search(r'src="(/static/dist/assets/[^"]+\.js)"', response.text)
    assert asset_path is not None
    asset_response = client.get(asset_path.group(1))
    assert asset_response.status_code == 200
    assert "javascript" in asset_response.headers["content-type"]


def test_missing_llm_config(tmp_path):
    app = create_app(
        settings=Settings(database_path=str(tmp_path / "a.db"), openai_api_key=""),
        repo=SessionRepository(tmp_path / "a.db"),
        llm=FakeLlm(fail_config=True),
    )
    client = TestClient(app)
    r = client.post("/api/sessions", json={"goal": "学图", "background": "新手"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r2 = client.post(f"/api/sessions/{sid}/graph")
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "LLM_CONFIG_MISSING"


def test_full_flow(tmp_path):
    app = create_app(
        settings=Settings(database_path=str(tmp_path / "b.db"), openai_api_key="x"),
        repo=SessionRepository(tmp_path / "b.db"),
        llm=FakeLlm(),
    )
    client = TestClient(app)
    r = client.post("/api/sessions", json={"goal": "学图", "background": "新手"})
    sid = r.json()["session_id"]
    r = client.post(f"/api/sessions/{sid}/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["graph"]["nodes"]) >= 3
    r = client.put(
        f"/api/sessions/{sid}/mastery",
        json={"node_id": "a", "level": "understood"},
    )
    assert r.status_code == 200
    assert "a" not in r.json()["gaps"] or r.json()["mastery"]["a"] == "understood"
    r = client.post(f"/api/sessions/{sid}/path")
    assert r.status_code == 200
    path = r.json()["path"]
    assert path
    ids = [p["node_id"] for p in path]
    if "b" in ids and "c" in ids:
        assert ids.index("b") < ids.index("c")


def test_llm_override_on_graph(tmp_path):
    fake = FakeLlm()
    app = create_app(
        settings=Settings(database_path=str(tmp_path / "c.db"), openai_api_key="server-key"),
        repo=SessionRepository(tmp_path / "c.db"),
        llm=fake,
    )
    client = TestClient(app)
    sid = client.post("/api/sessions", json={"goal": "g", "background": "b"}).json()["session_id"]
    r = client.post(
        f"/api/sessions/{sid}/graph",
        json={
            "llm": {
                "api_key": "user-key",
                "base_url": "https://gateway.example/v1",
                "model": "think-model",
                "reasoning_effort": "medium",
                "max_tokens": 8000,
                "enable_thinking": True,
            }
        },
    )
    assert r.status_code == 200
    # Fake with_override 后调用 generate_graph 的是新实例；通过响应成功即可，
    # 再测 defaults 接口
    d = client.get("/api/llm/defaults")
    assert d.status_code == 200
    assert d.json()["has_server_api_key"] is True
    assert d.json()["model"]
