"""One-shot symbolic memory graph command handlers."""

from __future__ import annotations

import argparse

from nuself.cli.application import cli_application
from nuself.memory.repository import (
    SymbolicGraphEdge,
    SymbolicGraphEdgeFilters,
    SymbolicGraphNode,
    SymbolicGraphNodeFilters,
)


def _format_node(node: SymbolicGraphNode) -> str:
    return f"{node.id} [{node.kind}:{node.type}] {node.label}"


def _format_edge(edge: SymbolicGraphEdge) -> str:
    return (
        f"{edge.id} {edge.source} --{edge.relation}-> "
        f"{edge.target} confidence={edge.confidence:.2f}"
    )


def handle_memory_graph_nodes(args: argparse.Namespace) -> int:
    nodes = cli_application().memory.list_graph_nodes(
        SymbolicGraphNodeFilters(type=args.type)
    )
    if not nodes:
        print("No symbolic graph nodes.")
        return 0
    for node in nodes:
        print(_format_node(node))
    return 0


def handle_memory_graph_edges(args: argparse.Namespace) -> int:
    edges = cli_application().memory.list_graph_edges(
        SymbolicGraphEdgeFilters(
            relation=args.relation,
            source_id=args.source_id,
            target_id=args.target_id,
        )
    )
    if not edges:
        print("No symbolic graph edges.")
        return 0
    for edge in edges:
        print(_format_edge(edge))
    return 0


def handle_memory_graph_search(args: argparse.Namespace) -> int:
    result = cli_application().memory.search_graph(
        args.query,
        node_type=args.type,
        limit=args.limit,
        depth=args.depth,
    )
    if not result.nodes:
        print("No symbolic graph matches.")
        return 0
    print("Nodes:")
    for node in result.nodes:
        print(_format_node(node))
    if result.edges:
        print("Edges:")
        for edge in result.edges:
            print(_format_edge(edge))
    return 0


def handle_memory_graph_path(args: argparse.Namespace) -> int:
    path = cli_application().memory.find_graph_path(
        args.from_id, args.to_id
    )
    if not path:
        print("No path found.")
        return 0
    print("Path:")
    for edge in path:
        print(_format_edge(edge))
    return 0


def handle_memory_graph_closure(
    args: argparse.Namespace,
) -> int:
    if args.relation is None:
        print("--relation is required for closure.")
        return 1
    result = cli_application().memory.graph_closure(
        args.node_id, args.relation
    )
    if not result.nodes:
        print("No closure nodes.")
        return 0
    print("Nodes:")
    for node in result.nodes:
        print(_format_node(node))
    if result.edges:
        print("Edges:")
        for edge in result.edges:
            print(_format_edge(edge))
    return 0
