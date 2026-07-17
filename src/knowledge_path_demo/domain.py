"""领域纯函数：掌握档次、图校验、缺口与路径拓扑。"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MasteryLevel(str, Enum):
    """五档掌握度。"""

    unknown = "unknown"  # 不了解
    heard = "heard"  # 了解
    understood = "understood"  # 掌握
    proficient = "proficient"  # 熟练掌握
    expert = "expert"  # 精通


# 数值序：低于 understood 视为缺口
MASTERY_ORDER: dict[MasteryLevel, int] = {
    MasteryLevel.unknown: 0,
    MasteryLevel.heard: 1,
    MasteryLevel.understood: 2,
    MasteryLevel.proficient: 3,
    MasteryLevel.expert: 4,
}

GAP_THRESHOLD = MASTERY_ORDER[MasteryLevel.understood]

# 默认放宽：长链路主题需要更深依赖；仍可用参数收紧
DEFAULT_MAX_NODES = 80
DEFAULT_MAX_DEPTH = 24


class GraphInvalidError(ValueError):
    """依赖图结构非法。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class KnowledgeNode:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class KnowledgeEdge:
    """硬前置边：from_id 是 to_id 的前置。"""

    from_id: str
    to_id: str


@dataclass(frozen=True)
class KnowledgeGraph:
    nodes: tuple[KnowledgeNode, ...]
    edges: tuple[KnowledgeEdge, ...]


@dataclass(frozen=True)
class PathItem:
    node_id: str
    title: str
    actions: tuple[str, ...]
    acceptance_question: str


def mastery_rank(level: MasteryLevel | str) -> int:
    """掌握档次序数值。"""
    if isinstance(level, str):
        level = MasteryLevel(level)
    return MASTERY_ORDER[level]


def is_gap(level: MasteryLevel | str) -> bool:
    """是否低于掌握阈值。"""
    return mastery_rank(level) < GAP_THRESHOLD


def validate_graph(
    graph: KnowledgeGraph,
    *,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> None:
    """校验 DAG、节点数与深度；非法则抛 GraphInvalidError。"""
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    if not nodes:
        raise GraphInvalidError("GRAPH_INVALID", "节点列表为空")
    if len(nodes) > max_nodes:
        raise GraphInvalidError(
            "GRAPH_INVALID", f"节点数 {len(nodes)} 超过上限 {max_nodes}"
        )

    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        raise GraphInvalidError("GRAPH_INVALID", "节点 ID 不唯一")
    id_set = set(ids)

    for e in edges:
        if e.from_id not in id_set or e.to_id not in id_set:
            raise GraphInvalidError(
                "GRAPH_INVALID", f"边引用未知节点: {e.from_id}->{e.to_id}"
            )
        if e.from_id == e.to_id:
            raise GraphInvalidError("GRAPH_INVALID", f"自环: {e.from_id}")

    # 邻接：前置 -> 后继
    successors: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {i: 0 for i in id_set}
    for e in edges:
        successors[e.from_id].append(e.to_id)
        indegree[e.to_id] += 1

    # Kahn 拓扑检测环
    q = deque([i for i, d in indegree.items() if d == 0])
    seen = 0
    while q:
        u = q.popleft()
        seen += 1
        for v in successors[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    if seen != len(id_set):
        raise GraphInvalidError("GRAPH_INVALID", "依赖图存在环")

    # 深度：从入度为 0 的根沿后继边的最长路径
    roots = [i for i in id_set if all(e.to_id != i for e in edges)]
    if not roots:
        roots = list(id_set)

    memo: dict[str, int] = {}

    def depth_of(nid: str, stack: set[str]) -> int:
        if nid in memo:
            return memo[nid]
        if nid in stack:
            raise GraphInvalidError("GRAPH_INVALID", "依赖图存在环")
        stack.add(nid)
        kids = successors.get(nid, [])
        d = 1 if not kids else 1 + max(depth_of(c, stack) for c in kids)
        stack.remove(nid)
        memo[nid] = d
        return d

    max_d = max(depth_of(r, set()) for r in roots)
    if max_d > max_depth:
        raise GraphInvalidError(
            "GRAPH_INVALID", f"图深度 {max_d} 超过上限 {max_depth}"
        )


def compute_gaps(
    node_ids: Iterable[str],
    mastery: dict[str, MasteryLevel | str],
) -> list[str]:
    """返回缺口节点 ID 列表。"""
    gaps: list[str] = []
    for nid in node_ids:
        level = mastery.get(nid, MasteryLevel.unknown)
        if is_gap(level):
            gaps.append(nid)
    return gaps


def topological_order(graph: KnowledgeGraph, subset: set[str] | None = None) -> list[str]:
    """对全图或子集做拓扑排序；子集内边约束保留。"""
    id_set = {n.id for n in graph.nodes}
    if subset is not None:
        id_set = id_set & subset

    successors: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {i: 0 for i in id_set}
    for e in graph.edges:
        if e.from_id in id_set and e.to_id in id_set:
            successors[e.from_id].append(e.to_id)
            indegree[e.to_id] += 1

    q = deque(sorted([i for i, d in indegree.items() if d == 0]))
    order: list[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in sorted(successors[u]):
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    if len(order) != len(id_set):
        raise GraphInvalidError("GRAPH_INVALID", "子集拓扑失败，可能有环")
    return order


def expand_gap_closure(
    graph: KnowledgeGraph,
    gaps: Iterable[str],
    mastery: dict[str, MasteryLevel | str],
) -> set[str]:
    """缺口并上仍为缺口的硬前置祖先。"""
    # 后继 -> 前置列表
    prereqs: dict[str, list[str]] = defaultdict(list)
    for e in graph.edges:
        prereqs[e.to_id].append(e.from_id)

    result: set[str] = set()
    stack = list(gaps)
    while stack:
        nid = stack.pop()
        if nid in result:
            continue
        result.add(nid)
        for p in prereqs.get(nid, []):
            level = mastery.get(p, MasteryLevel.unknown)
            if is_gap(level) and p not in result:
                stack.append(p)
    return result


def build_path_order(
    graph: KnowledgeGraph,
    mastery: dict[str, MasteryLevel | str],
) -> list[str]:
    """计算补缺路径节点顺序。"""
    all_ids = [n.id for n in graph.nodes]
    gaps = compute_gaps(all_ids, mastery)
    closure = expand_gap_closure(graph, gaps, mastery)
    return topological_order(graph, closure)
