from papergraph.models import (
    DEPENDENCY_EXTRACTION_BASIS,
    EMPTY_DEPENDENCY_WARNING,
    TheoremNode,
)


def recursive_reference_ids(root: str, adjacency: dict[str, list[str]]) -> list[str]:
    """Preserve reference DFS order without Python recursion or DAG assumptions."""
    result, visited = [], set()
    stack = [iter(adjacency.get(root, []))]
    while stack:
        target = next(stack[-1], None)
        if target is None:
            stack.pop()
        elif target not in visited:
            visited.add(target)
            result.append(target)
            stack.append(iter(adjacency.get(target, [])))
    return result


class PaperGraph:
    def __init__(self, nodes: list[TheoremNode]):
        self.nodes = nodes
        self.by_id = {
            node.id: node
            for node in nodes
        }

    def get(self, theorem_id: str) -> TheoremNode:
        try:
            return self.by_id[theorem_id]
        except KeyError:
            raise KeyError(
                f"Unknown theorem id: {theorem_id}"
            ) from None

    def dependencies(
        self,
        theorem_id: str,
        recursive: bool = False,
    ) -> list[TheoremNode]:
        root = self.get(theorem_id)

        direct_ids = [
            ref
            for ref in root.refs
            if ref in self.by_id
        ]

        if not recursive:
            return [
                self.by_id[node_id]
                for node_id in direct_ids
            ]

        adjacency = {node.id: [ref for ref in node.refs if ref in self.by_id] for node in self.nodes}
        return [self.by_id[node_id] for node_id in recursive_reference_ids(theorem_id, adjacency)]

    def where_used(
        self,
        theorem_id: str,
    ) -> list[TheoremNode]:
        self.get(theorem_id)

        result = []

        for node in self.nodes:
            if theorem_id in node.refs:
                result.append(node)

        return result

    def dependency_diagnostics(
        self,
        theorem_id: str,
        recursive: bool = False,
    ) -> dict:
        root = self.get(theorem_id)
        dependencies = self.dependencies(
            theorem_id,
            recursive=recursive,
        )
        dependency_ids = [
            node.id
            for node in dependencies
        ]
        resolved_labels = [
            ref
            for ref in root.refs
            if ref in self.by_id
        ]
        unresolved_labels = [
            ref
            for ref in root.refs
            if ref not in self.by_id
        ]
        warnings = []
        if not dependency_ids:
            warnings.append(EMPTY_DEPENDENCY_WARNING)
        return {
            "theorem_id": theorem_id,
            "recursive": recursive,
            "extraction_basis": DEPENDENCY_EXTRACTION_BASIS,
            "referenced_labels": list(root.refs),
            "resolved_labels": resolved_labels,
            "unresolved_labels": unresolved_labels,
            "dependency_ids": dependency_ids,
            "warnings": warnings,
        }
