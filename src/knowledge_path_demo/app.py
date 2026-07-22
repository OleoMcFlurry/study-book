"""FastAPI 应用与 API。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from knowledge_path_demo.config import Settings
from knowledge_path_demo.domain import (
    GraphInvalidError,
    MasteryLevel,
    build_path_order,
    compute_gaps,
    validate_graph,
)
from knowledge_path_demo.llm import (
    LlmCallOptions,
    LlmClient,
    LlmError,
    graph_from_dict,
    graph_to_dict,
)
from knowledge_path_demo.repository import SessionRepository

ReasoningEffortField = Literal["none", "low", "medium", "high"]


class CreateSessionBody(BaseModel):
    goal: str = Field(min_length=1)
    background: str = Field(default="")
    known_keywords: list[str] = Field(default_factory=list)


class MasteryBody(BaseModel):
    node_id: str
    level: MasteryLevel


class LlmOverrideBody(BaseModel):
    """请求级 LLM 覆盖；兼容任意 chat completions 协议网关。"""

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffortField | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    enable_thinking: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


class GenerateBody(BaseModel):
    llm: LlmOverrideBody | None = None


def create_app(
    settings: Settings | None = None,
    repo: SessionRepository | None = None,
    llm: LlmClient | None = None,
) -> FastAPI:
    settings = settings or Settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = repo or SessionRepository(db_path)
    default_opts = LlmCallOptions(
        reasoning_effort=_safe_effort(settings.llm_reasoning_effort),
        max_tokens=settings.llm_max_tokens or None,
        enable_thinking=settings.llm_enable_thinking,
    )
    llm = llm or LlmClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        default_options=default_opts,
        max_nodes=settings.graph_max_nodes,
        max_depth=settings.graph_max_depth,
    )
    # 统一应用图约束（含测试注入的 FakeLlm）
    llm.max_nodes = settings.graph_max_nodes
    llm.max_depth = settings.graph_max_depth

    app = FastAPI(title="知识路径学习 Demo")
    dist_dir = Path(__file__).parent / "static" / "dist"
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        raise RuntimeError("前端构建产物不存在，请先在 frontend 目录执行 pnpm build")
    app.mount(
        "/static/dist",
        StaticFiles(directory=str(dist_dir)),
        name="frontend-static",
    )

    app.state.repo = repo
    app.state.llm = llm
    app.state.settings = settings

    @app.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/api/llm/defaults")
    def llm_defaults() -> dict[str, Any]:
        """返回可公开的默认配置（不含完整密钥）。"""
        return {
            "base_url": settings.openai_base_url,
            "model": settings.openai_model,
            "has_server_api_key": bool(settings.openai_api_key.strip()),
            "reasoning_effort": _safe_effort(settings.llm_reasoning_effort),
            "max_tokens": settings.llm_max_tokens or None,
            "enable_thinking": settings.llm_enable_thinking,
        }

    @app.post("/api/sessions")
    def create_session(body: CreateSessionBody) -> dict[str, Any]:
        rec = repo.create(body.goal.strip(), body.background.strip(), body.known_keywords)
        return _session_view(rec)

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        rec = repo.get(session_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
        return _session_view(rec)

    @app.post("/api/sessions/{session_id}/graph")
    def generate_graph(
        session_id: str,
        body: GenerateBody = Body(default_factory=GenerateBody),
    ) -> dict[str, Any]:
        rec = repo.get(session_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
        client, opts = _resolve_llm(llm, body.llm)
        try:
            graph = client.generate_graph(
                rec.goal, rec.background, rec.known_keywords, options=opts
            )
            validate_graph(
                graph,
                max_nodes=settings.graph_max_nodes,
                max_depth=settings.graph_max_depth,
            )
            data = graph_to_dict(graph)
            mastery = dict(rec.mastery_json)
            for n in graph.nodes:
                mastery.setdefault(n.id, MasteryLevel.unknown.value)
            repo.save_mastery(session_id, mastery)
            rec = repo.save_graph(session_id, data)
        except LlmError as exc:
            status = 400 if exc.code == "LLM_CONFIG_MISSING" else 502
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc
        except GraphInvalidError as exc:
            raise HTTPException(
                status_code=422, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        return _session_view(rec)

    @app.put("/api/sessions/{session_id}/mastery")
    def update_mastery(session_id: str, body: MasteryBody) -> dict[str, Any]:
        rec = repo.get(session_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
        if not rec.graph_json:
            raise HTTPException(status_code=409, detail={"code": "NO_GRAPH", "message": "尚未生成依赖图"})
        node_ids = {n["id"] for n in rec.graph_json.get("nodes", [])}
        if body.node_id not in node_ids:
            raise HTTPException(status_code=404, detail={"code": "NODE_NOT_FOUND", "message": "节点不存在"})
        mastery = dict(rec.mastery_json)
        mastery[body.node_id] = body.level.value
        rec = repo.save_mastery(session_id, mastery)
        graph = graph_from_dict(rec.graph_json)
        gaps = compute_gaps([n.id for n in graph.nodes], mastery)
        view = _session_view(rec)
        view["gaps"] = gaps
        return view

    @app.post("/api/sessions/{session_id}/path")
    def generate_path(
        session_id: str,
        body: GenerateBody = Body(default_factory=GenerateBody),
    ) -> dict[str, Any]:
        rec = repo.get(session_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "会话不存在"})
        if not rec.graph_json:
            raise HTTPException(status_code=409, detail={"code": "NO_GRAPH", "message": "尚未生成依赖图"})
        graph = graph_from_dict(rec.graph_json)
        order_ids = build_path_order(graph, rec.mastery_json)
        by_id = {n.id: n for n in graph.nodes}
        ordered_nodes = [by_id[i] for i in order_ids if i in by_id]
        client, opts = _resolve_llm(llm, body.llm)
        try:
            items = client.generate_path_items(rec.goal, ordered_nodes, options=opts)
        except LlmError as exc:
            status = 400 if exc.code == "LLM_CONFIG_MISSING" else 502
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc
        path_data = [
            {
                "node_id": it.node_id,
                "title": it.title,
                "actions": list(it.actions),
                "acceptance_question": it.acceptance_question,
            }
            for it in items
        ]
        rec = repo.save_path(session_id, path_data)
        return _session_view(rec)

    return app


def _safe_effort(value: str) -> ReasoningEffortField:
    if value in ("none", "low", "medium", "high"):
        return value  # type: ignore[return-value]
    return "none"


def _resolve_llm(
    base: LlmClient, override: LlmOverrideBody | None
) -> tuple[LlmClient, LlmCallOptions]:
    """合并服务端默认与请求覆盖。"""
    if override is None:
        return base, base.default_options

    # 仅当字段为 null/省略时沿用服务端密钥；显式传空字符串会触发配置缺失错误。
    if override.api_key is not None:
        key_arg: str | None = override.api_key.strip()
    else:
        key_arg = None

    base_url = override.base_url.strip() if override.base_url else None
    model = override.model.strip() if override.model else None

    effort = (
        override.reasoning_effort
        if override.reasoning_effort is not None
        else base.default_options.reasoning_effort
    )
    max_tokens = (
        override.max_tokens
        if override.max_tokens is not None
        else base.default_options.max_tokens
    )
    enable_thinking = (
        override.enable_thinking
        if override.enable_thinking is not None
        else base.default_options.enable_thinking
    )
    temperature = (
        override.temperature
        if override.temperature is not None
        else base.default_options.temperature
    )
    opts = LlmCallOptions(
        reasoning_effort=effort,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
        temperature=temperature,
    )
    client = base.with_override(
        api_key=key_arg if override.api_key is not None else None,
        base_url=base_url,
        model=model,
        options=opts,
    )
    return client, opts


def _session_view(rec: Any) -> dict[str, Any]:
    gaps: list[str] = []
    if rec.graph_json:
        graph = graph_from_dict(rec.graph_json)
        gaps = compute_gaps([n.id for n in graph.nodes], rec.mastery_json)
    return {
        "session_id": rec.id,
        "goal": rec.goal,
        "background": rec.background,
        "known_keywords": rec.known_keywords,
        "status": rec.status,
        "graph": rec.graph_json,
        "mastery": rec.mastery_json,
        "path": rec.path_json,
        "gaps": gaps,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }


app = create_app()
