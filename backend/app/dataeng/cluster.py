"""Group raw values that mean the same thing — OpenRefine's key-collision method.

Client spreadsheets spell one channel a dozen ways ("TMALL", "T-Mall", "tmall  ",
"天猫 旗舰店"). Reviewing those one row at a time is the slowest part of building an
enum map, and it is the part a deterministic algorithm is actually good at.

Two keying functions, both from OpenRefine, are applied in order:

* **fingerprint** — case-fold, drop punctuation, split into tokens, sort and
  de-duplicate them, re-join. Collapses word order, spacing and punctuation noise.
* **n-gram fingerprint** — the sorted set of character 2-grams. Catches the rest
  (missing separators, CJK strings that have no whitespace to tokenise on).

The result is a *proposal*: values that collided, with the most frequent spelling
as the suggested canonical form. A human still accepts it — the mapping written
into the pipeline is the reviewed one, never the raw clustering output.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

NGRAM_SIZE = 2
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE = re.compile(r"\s+", flags=re.UNICODE)


@dataclass
class ValueCluster:
    """Raw spellings judged to denote the same value."""
    key: str
    method: str                       # fingerprint | ngram
    suggestion: str                   # most frequent member — the proposed canonical
    values: list[tuple[str, int]] = field(default_factory=list)  # (raw, row count)

    @property
    def rows(self) -> int:
        return sum(n for _, n in self.values)


def fingerprint(value: str) -> str:
    """Order-, case- and punctuation-insensitive key for a value."""
    norm = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    norm = _PUNCT.sub(" ", norm)
    tokens = sorted(set(_SPACE.split(norm.strip())))
    return " ".join(t for t in tokens if t)


def ngram_fingerprint(value: str, size: int = NGRAM_SIZE) -> str:
    """Sorted set of character n-grams — a fingerprint that needs no word breaks."""
    norm = unicodedata.normalize("NFKC", str(value)).casefold()
    norm = _PUNCT.sub("", norm)
    norm = _SPACE.sub("", norm)
    if len(norm) < size:
        return norm
    return "".join(sorted({norm[i:i + size] for i in range(len(norm) - size + 1)}))


def cluster_values(values: list[tuple[str, int]]) -> list[ValueCluster]:
    """Cluster ``(raw value, row count)`` pairs into groups worth reviewing.

    Both keying functions are applied to every value and the resulting buckets are
    merged transitively, so a value keeps whichever method connects it. Running the
    methods in sequence instead would fragment real groups: ``TMALL`` and ``tmall``
    share a fingerprint while ``T-Mall`` only reaches them through n-grams, and it
    would be stranded once the fingerprint pass had claimed the other two.

    Only groups with more than one distinct spelling are returned — a value nothing
    collides with needs no decision. Groups come back heaviest first, so the ones
    covering the most rows are reviewed first.
    """
    counts: dict[str, int] = {}
    for raw, n in values:
        value = str(raw)
        if value.strip():
            counts[value] = counts.get(value, 0) + int(n)
    if not counts:
        return []

    merge = _Merge(counts)
    fp_keys = merge.absorb(fingerprint)
    merge.absorb(ngram_fingerprint)

    out: list[ValueCluster] = []
    for members in merge.groups():
        if len(members) < 2:
            continue
        ordered = sorted(((v, counts[v]) for v in members), key=lambda kv: (-kv[1], kv[0]))
        keys = {fp_keys[v] for v in members}
        exact = len(keys) == 1
        out.append(ValueCluster(
            key=next(iter(keys)) if exact else ngram_fingerprint(ordered[0][0]),
            method="fingerprint" if exact else "ngram",
            suggestion=ordered[0][0], values=ordered))
    out.sort(key=lambda g: (-g.rows, g.suggestion))
    return out


class _Merge:
    """Union-find over the raw values, keyed by one or more fingerprint functions."""

    def __init__(self, values) -> None:
        self._parent = {v: v for v in values}

    def _root(self, value: str) -> str:
        while self._parent[value] != value:
            self._parent[value] = self._parent[self._parent[value]]
            value = self._parent[value]
        return value

    def absorb(self, key_of) -> dict[str, str]:
        """Union everything sharing a key. Returns each value's key."""
        keys: dict[str, str] = {}
        buckets: dict[str, str] = {}   # key → first value seen with it
        for value in list(self._parent):
            key = key_of(value)
            keys[value] = key
            if not key:
                continue
            first = buckets.setdefault(key, value)
            a, b = self._root(first), self._root(value)
            if a != b:
                self._parent[b] = a
        return keys

    def groups(self) -> list[list[str]]:
        out: dict[str, list[str]] = {}
        for value in self._parent:
            out.setdefault(self._root(value), []).append(value)
        return list(out.values())
