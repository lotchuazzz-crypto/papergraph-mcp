from dataclasses import dataclass


@dataclass(slots=True)
class TheoremNode:
    id: str
    kind: str
    title: str | None
    label: str | None
    content: str
    refs: tuple[str, ...]
    position: int

    def summary(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "label": self.label,
            "refs": list(self.refs),
        }

    def full(self) -> dict:
        return {
            **self.summary(),
            "content": self.content,
        }