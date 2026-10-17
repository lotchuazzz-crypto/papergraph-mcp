"""Read tutorial contracts through the navigation users actually follow."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def linked_document(source: Path, target: str) -> str:
    links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', source.read_text(encoding='utf-8'))
    assert target in links, (source, target)
    path = (source.parent / target.split('#', 1)[0]).resolve()
    assert path.is_relative_to(ROOT) and path.is_file(), (source, target)
    return path.read_text(encoding='utf-8')
