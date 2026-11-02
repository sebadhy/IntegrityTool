"""Keep the developer's entry points navigable in a checkout and on GitHub."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.name)
def test_relative_document_links_exist(document):
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path:
            continue
        path = (document.parent / unquote(parsed.path)).resolve()
        assert path.is_relative_to(ROOT), f"{document.name}: link outside repository"
        assert path.exists(), f"{document.name}: missing relative link {target}"
