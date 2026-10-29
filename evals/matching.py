"""Key-term matching shared by answer_eval.py (does the answer state the fact?) and
calibrate_retrieval.py (does a retrieved chunk contain the fact?), so both measure facts the
same way.
"""

import re

_NUMBER_TERM = re.compile(r"\d+(?:\.\d+)?")

# Curly quotes and en/em dashes -> ASCII, so a curly "can't" matches "can't" (code points, not
# literals, to keep them visible in review).
_ASCII_PUNCTUATION = str.maketrans(
    {
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x201C): '"',
        chr(0x201D): '"',
        chr(0x2013): "-",
        chr(0x2014): "-",
    }
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ASCII_PUNCTUATION)).strip().lower()


def term_matches(term: str, text: str) -> bool:
    """`text` should already be normalized (and, for answers, citation-marker-free). A purely
    numeric alternative matches only as a whole number; "a|b" passes if either matches.
    """
    for alternative in (normalize(a) for a in term.split("|")):
        if _NUMBER_TERM.fullmatch(alternative):
            digits = text.replace(",", "")
            if re.search(rf"(?<![\d.]){re.escape(alternative)}(?![\d]|\.\d)", digits):
                return True
        elif alternative and alternative in text:
            return True
    return False


def contains_all_terms(key_terms: list[str], text: str) -> bool:
    normalized = normalize(text)
    return all(term_matches(t, normalized) for t in key_terms)
