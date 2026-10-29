"""Guards on the policy corpus that the Knowledge Base ingests (data/policies)."""

from pathlib import Path

POLICIES_DIR = Path(__file__).resolve().parents[4] / "data" / "policies"


def test_policy_docs_exist() -> None:
    assert len(list(POLICIES_DIR.glob("*.md"))) == 6


def test_policy_docs_contain_no_markdown_tables() -> None:
    # For .md pages containing a table, Bedrock replaces a matching chunk with the full page or
    # table at retrieval (kb-chunking.html, "Tables and figures in parsed content"), so these
    # short docs came back whole (~600-720 tokens). Write tabular facts as bullet lists.
    # See DECISIONS.md, "Policy docs avoid markdown tables" and the Incidents entry.
    offenders = [
        f"{path.name}:{n}: {line.strip()[:60]}"
        for path in sorted(POLICIES_DIR.glob("*.md"))
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if line.lstrip().startswith("|")
    ]
    assert offenders == []
