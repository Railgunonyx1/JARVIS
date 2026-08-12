"""Knowledge Graph — JARVIS MK-X Part 27.

Entity extraction, relation mapping, and graph queries backed by SQLite.
Connects memory, context, and reasoning into a unified knowledge layer.
"""

from knowledge_graph.entity_extractor import EntityExtractor, extract_entities
from knowledge_graph.graph import KnowledgeGraph, get_knowledge_graph
from knowledge_graph.query import GraphQuery, query_graph
from knowledge_graph.relation_mapper import RelationMapper, extract_relations

__all__ = [
    "KnowledgeGraph", "get_knowledge_graph",
    "EntityExtractor", "extract_entities",
    "RelationMapper", "extract_relations",
    "GraphQuery", "query_graph",
]
