"""Deterministic metadata normalization.

The AI analyzer is prompt-guided and can return loose values ("second sem",
"freshman", "emete1112"). This module enforces consistent canonical forms in
code, so stored metadata never depends on the model's phrasing.
"""

from __future__ import annotations

import re

# ── Semester ────────────────────────────────────────────────────────────────

_SEMESTER_RULES = [
    (re.compile(r"\b(1st|first|one)\b|^\s*1\s*$|\bsem\.?\s*(?:no\.?\s*)?1\b|\bsemester\s+i\b|\bsem\.?\s+i\b|\bsem\.?i\b"), "First Semester"),
    (re.compile(r"\b(2nd|second|two)\b|^\s*2\s*$|\bsem\.?\s*(?:no\.?\s*)?2\b|\bsemester\s+ii\b|\bsem\.?\s+ii\b|\bsem\.?ii\b"), "Second Semester"),
    (re.compile(r"\b(3rd|third|three)\b|^\s*3\s*$|\bsem\.?\s*(?:no\.?\s*)?3\b|\bsemester\s+iii\b|\bsem\.?\s+iii\b|\bsem\.?iii\b"), "Third Semester"),
]


def normalize_semester(value: str | None) -> str | None:
    """Map loose semester phrasing to a canonical term name."""
    if not value or not str(value).strip():
        return value
    text = str(value).strip().lower()
    for pattern, canonical in _SEMESTER_RULES:
        if pattern.search(text):
            return canonical
    return str(value).strip().title()


# ── Study year ──────────────────────────────────────────────────────────────

_YEAR_WORDS = {
    "freshman": 1,
    "fresher": 1,
    "sophomore": 2,
    "junior": 3,
    "senior": 4,
}
_YEAR_ORDINALS = {
    "1st": 1, "first": 1, "one": 1,
    "2nd": 2, "second": 2, "two": 2,
    "3rd": 3, "third": 3, "three": 3,
    "4th": 4, "fourth": 4, "four": 4,
    "5th": 5, "fifth": 5, "five": 5,
    "6th": 6, "sixth": 6, "six": 6,
}


def normalize_study_year(value: str | None) -> str | None:
    """Map freshman / '1st year' / 'y1' / '2' etc. to canonical 'Year N'."""
    if not value or not str(value).strip():
        return value
    text = str(value).strip().lower()

    lowered = text.replace("-", " ")
    if "post" in lowered and ("grad" in lowered or "graduate" in lowered):
        return "Postgraduate"
    if "graduate" in lowered or "masters" in lowered or "msc" in lowered:
        return "Postgraduate"

    match = re.search(r"\byear\s*:?\s*(\d)\b", lowered)
    if match:
        return f"Year {match.group(1)}"

    match = re.search(r"\by\s*:?\s*(\d)\b", lowered)
    if match:
        return f"Year {match.group(1)}"

    match = re.fullmatch(r"\s*(\d)\s*", lowered)
    if match:
        return f"Year {match.group(1)}"

    match = re.search(r"\b(\d)(?:st|nd|rd|th)?\s+year\b", lowered)
    if match:
        return f"Year {match.group(1)}"

    for word, number in _YEAR_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return f"Year {number}"

    for word, number in _YEAR_ORDINALS.items():
        if re.search(rf"\b{word}\b", lowered):
            return f"Year {number}"

    return str(value).strip().title()


# ── Course code ─────────────────────────────────────────────────────────────

_COURSE_CODE = re.compile(r"^([A-Z]{2,7})\s*(\d{2,5}[A-Z]?)$")


def normalize_course_code(value: str | None) -> str | None:
    """Canonicalize course codes to 'PREFIX NUMBER' upper-case form.

    Examples: 'emete1112' → 'EMETE 1112', 'math-1014' → 'MATH 1014',
    'ceng 2082 (old)' keeps free-text suffixes intact but normalizes the code
    portion.
    """
    if not value or not str(value).strip():
        return value
    text = str(value).strip()
    match = _COURSE_CODE.match(re.sub(r"[\s_-]+", " ", text).upper())
    if match:
        return f"{match.group(1)} {match.group(2)}"
    # Code with trailing parenthetical/suffix: normalize just the leading code.
    head_match = re.match(
        r"^([A-Za-z]{2,7})[\s_-]*(\d{2,5}[A-Za-z]?)\b(.*)$", text
    )
    if head_match:
        tail = head_match.group(3).strip()
        normalized = f"{head_match.group(1).upper()} {head_match.group(2).upper()}"
        return f"{normalized} {tail}" if tail else normalized
    return text.upper() if len(text) <= 20 else text


# ── Exam type ───────────────────────────────────────────────────────────────

_EXAM_TYPES = {
    "final": "Final",
    "finalexam": "Final",
    "mid": "Midterm",
    "midterm": "Midterm",
    "mid-sem": "Midterm",
    "quiz": "Quiz",
    "quizzes": "Quiz",
    "test": "Quiz",
    "assignment": "Assignment",
    "hw": "Assignment",
    "homework": "Assignment",
}


def normalize_exam_type(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return value
    key = re.sub(r"[^a-z]", "", str(value).lower())
    return _EXAM_TYPES.get(key, str(value).strip().title())
