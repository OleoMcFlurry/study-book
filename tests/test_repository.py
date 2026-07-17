"""仓储测试。"""

from knowledge_path_demo.repository import SessionRepository


def test_create_and_reload(tmp_path):
    db = tmp_path / "t.db"
    repo = SessionRepository(db)
    rec = repo.create("目标", "背景", ["k1"])
    assert rec.status == "created"
    repo2 = SessionRepository(db)
    loaded = repo2.get(rec.id)
    assert loaded is not None
    assert loaded.goal == "目标"
    assert loaded.known_keywords == ["k1"]


def test_save_graph_and_mastery(tmp_path):
    repo = SessionRepository(tmp_path / "t.db")
    rec = repo.create("g", "b")
    graph = {
        "nodes": [{"id": "a", "title": "A", "description": ""}],
        "edges": [],
    }
    rec = repo.save_graph(rec.id, graph)
    assert rec.status == "graph_ready"
    assert rec.graph_json["nodes"][0]["id"] == "a"
    rec = repo.save_mastery(rec.id, {"a": "heard"})
    assert rec.mastery_json["a"] == "heard"
