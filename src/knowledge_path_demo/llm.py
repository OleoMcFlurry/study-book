"""OpenAI Chat Completions 兼容客户端；支持请求级覆盖。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from knowledge_path_demo.domain import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    PathItem,
    validate_graph,
)

ReasoningEffort = Literal["none", "low", "medium", "high"]


class LlmError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LlmCallOptions:
    """单次调用可选参数：思考强度与上下文/输出窗口。"""

    # none 表示不在请求体中发送 reasoning 相关字段
    reasoning_effort: ReasoningEffort = "none"
    # 输出上限；部分厂商用 max_completion_tokens
    max_tokens: int | None = None
    # 是否同时发送 enable_thinking（兼容部分国产 chat 网关）
    enable_thinking: bool = False
    temperature: float | None = 0.2


class LlmClient:
    """调用 /chat/completions 并解析 JSON。"""

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        default_options: LlmCallOptions | None = None,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = (model or "gpt-4o-mini").strip()
        self.timeout = timeout
        self.default_options = default_options or LlmCallOptions()
        self.max_nodes = max_nodes
        self.max_depth = max_depth

    def with_override(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        options: LlmCallOptions | None = None,
        max_nodes: int | None = None,
        max_depth: int | None = None,
    ) -> LlmClient:
        """基于当前客户端生成覆盖后的新客户端（不改原实例）。"""
        return LlmClient(
            api_key=api_key if api_key is not None else self.api_key,
            base_url=base_url if base_url is not None else self.base_url,
            model=model if model is not None else self.model,
            timeout=self.timeout,
            default_options=options if options is not None else self.default_options,
            max_nodes=max_nodes if max_nodes is not None else self.max_nodes,
            max_depth=max_depth if max_depth is not None else self.max_depth,
        )

    def ensure_configured(self) -> None:
        if not self.api_key:
            raise LlmError(
                "LLM_CONFIG_MISSING",
                "未配置 API Key：请在界面填写，或设置环境变量 OPENAI_API_KEY",
            )
        if not self.base_url:
            raise LlmError("LLM_CONFIG_MISSING", "未配置 Base URL")
        if not self.model:
            raise LlmError("LLM_CONFIG_MISSING", "未配置模型名称")

    def chat_json(
        self,
        system: str,
        user: str,
        options: LlmCallOptions | None = None,
    ) -> dict[str, Any]:
        self.ensure_configured()
        opts = options or self.default_options
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if opts.temperature is not None:
            body["temperature"] = opts.temperature
        if opts.max_tokens is not None and opts.max_tokens > 0:
            # 同时带两种字段，兼容不同 chat 协议实现
            body["max_tokens"] = opts.max_tokens
            body["max_completion_tokens"] = opts.max_tokens
        if opts.reasoning_effort and opts.reasoning_effort != "none":
            body["reasoning_effort"] = opts.reasoning_effort
        if opts.enable_thinking:
            body["enable_thinking"] = True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LlmError("LLM_CALL_FAILED", f"大模型调用失败: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("LLM_CALL_FAILED", "大模型响应结构异常") from exc

        # 部分思考模型 content 可能为空而把正文放在 reasoning 字段
        if content is None or (isinstance(content, str) and not content.strip()):
            msg = data["choices"][0]["message"]
            for key in ("reasoning_content", "reasoning"):
                alt = msg.get(key)
                if isinstance(alt, str) and alt.strip():
                    content = alt
                    break
        if not isinstance(content, str):
            raise LlmError("LLM_CALL_FAILED", "大模型 content 不是文本")

        return parse_json_content(content)

    def generate_graph(
        self,
        goal: str,
        background: str,
        known_keywords: list[str],
        options: LlmCallOptions | None = None,
    ) -> KnowledgeGraph:
        system = (
            "你是学习路径规划助手。根据用户目标生成通用领域的前置知识依赖图。"
            "只输出 JSON，字段 nodes[{id,title,description}], edges[{from,to}]，"
            "from 是 to 的硬前置。节点数 3-25，中文标题，id 用短英文蛇形。"
            "按用户背景控制基础深度，不要拆到无意义的原子知识。"
        )
        user = json.dumps(
            {
                "goal": goal,
                "background": background,
                "known_keywords": known_keywords,
            },
            ensure_ascii=False,
        )
        raw = self.chat_json(system, user, options=options)
        graph = graph_from_llm_dict(raw)
        validate_graph(graph, max_nodes=self.max_nodes, max_depth=self.max_depth)
        return graph

    def generate_path_items(
        self,
        goal: str,
        ordered_nodes: list[KnowledgeNode],
        options: LlmCallOptions | None = None,
    ) -> list[PathItem]:
        if not ordered_nodes:
            return []
        system = (
            "为每个知识节点生成学习动作与验收问句。输出 JSON："
            "items[{node_id,actions[],acceptance_question}]，中文。"
        )
        user = json.dumps(
            {
                "goal": goal,
                "nodes": [
                    {"id": n.id, "title": n.title, "description": n.description}
                    for n in ordered_nodes
                ],
            },
            ensure_ascii=False,
        )
        raw = self.chat_json(system, user, options=options)
        return path_items_from_llm(raw, ordered_nodes)


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise LlmError("LLM_CALL_FAILED", "无法解析大模型 JSON")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise LlmError("LLM_CALL_FAILED", "大模型 JSON 根类型必须是对象")
    return data


def graph_from_llm_dict(raw: dict[str, Any]) -> KnowledgeGraph:
    nodes_raw = raw.get("nodes") or []
    edges_raw = raw.get("edges") or []
    nodes = []
    for n in nodes_raw:
        nodes.append(
            KnowledgeNode(
                id=str(n["id"]),
                title=str(n.get("title") or n["id"]),
                description=str(n.get("description") or ""),
            )
        )
    edges = []
    for e in edges_raw:
        fr = e.get("from") if "from" in e else e.get("from_id")
        to = e.get("to") if "to" in e else e.get("to_id")
        edges.append(KnowledgeEdge(from_id=str(fr), to_id=str(to)))
    return KnowledgeGraph(nodes=tuple(nodes), edges=tuple(edges))


def path_items_from_llm(
    raw: dict[str, Any], ordered_nodes: list[KnowledgeNode]
) -> list[PathItem]:
    by_id = {n.id: n for n in ordered_nodes}
    items_raw = raw.get("items") or []
    mapped: dict[str, PathItem] = {}
    for it in items_raw:
        nid = str(it.get("node_id") or "")
        if nid not in by_id:
            continue
        actions = it.get("actions") or []
        if isinstance(actions, str):
            actions = [actions]
        q = str(it.get("acceptance_question") or f"能否用自己的话说明「{by_id[nid].title}」？")
        mapped[nid] = PathItem(
            node_id=nid,
            title=by_id[nid].title,
            actions=tuple(str(a) for a in actions) or (f"阅读并总结「{by_id[nid].title}」",),
            acceptance_question=q,
        )
    result: list[PathItem] = []
    for n in ordered_nodes:
        if n.id in mapped:
            result.append(mapped[n.id])
        else:
            result.append(
                PathItem(
                    node_id=n.id,
                    title=n.title,
                    actions=(f"针对目标学习「{n.title}」并做笔记",),
                    acceptance_question=f"能否解释「{n.title}」及其与目标的关系？",
                )
            )
    return result


def graph_to_dict(graph: KnowledgeGraph) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": n.id, "title": n.title, "description": n.description}
            for n in graph.nodes
        ],
        "edges": [{"from": e.from_id, "to": e.to_id} for e in graph.edges],
    }


def graph_from_dict(data: dict[str, Any]) -> KnowledgeGraph:
    return graph_from_llm_dict(data)
