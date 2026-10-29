"""Guards on the policy corpus that the Knowledge Base ingests (data/policies)."""

from pathlib import Path

POLICIES_DIR = Path(__file__).resolve().parents[4] / "data" / "policies"


def test_policy_docs_exist() -> None:
    assert len(list(POLICIES_DIR.glob("*.md"))) == 6


def test_policy_docs_contain_no_markdown_tables() -> None:
    # The KB's default parsing kept every table-containing file as one oversized chunk
    # (~600-720 tokens despite 300-token FIXED_SIZE chunking); converting a table to a list
    # split it normally. Write tabular facts as bullet lists. See DECISIONS.md Incidents.
    offenders = [
        f"{path.name}:{n}: {line.strip()[:60]}"
        for path in sorted(POLICIES_DIR.glob("*.md"))
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if line.lstrip().startswith("|")
    ]
    assert offenders == []
