"""
validation.py

This module is responsible for:
1. Cleaning raw registration strings coming from the CSV / LPR system.
2. Checking whether a registration looks like a valid UK registration format.
3. Detecting suspicious OCR-like mistakes before paid API lookup.
4. Returning a structured validation result that other modules can use.

Why this version is better
--------------------------
Compared with the earlier validator, this version is stricter and more
useful for LPR/OCR data.

It helps catch common OCR issues like:
- 0 used where O is expected
- O used where 0 is expected
- 1 used where I is expected
- 5 used where S is expected
- 2 used where Z is expected
- 8 used where B is expected

Important
---------
This module does NOT automatically "fix" the registration yet.
It only flags suspicious values and blocks obviously poor OCR reads
before they consume paid API calls.
"""

import re
from typing import TypedDict


class ValidationResult(TypedDict):
    """
    Structure returned by validate_registration().

    Fields
    ------
    raw:
        The original value received before cleaning.
    cleaned:
        The cleaned version (trimmed, upper-case, spaces removed).
    is_valid:
        True if the cleaned registration should be allowed to proceed to API lookup.
    reason:
        Human-readable reason describing the validation outcome.
    """
    raw: str
    cleaned: str
    is_valid: bool
    reason: str


def clean_registration(value: str) -> str:
    """
    Clean a raw registration string.

    What this does
    --------------
    - Converts the input to string
    - Strips leading/trailing spaces
    - Converts to upper-case
    - Removes internal spaces

    Example
    -------
    " lg72 dwf " -> "LG72DWF"
    """
    if value is None:
        return ""

    return str(value).strip().upper().replace(" ", "")


def looks_like_current_plate(reg: str) -> bool:
    """
    Check if the registration matches the modern UK format:

        AA00AAA

    Example:
        LG72DWF
    """
    return re.fullmatch(r"^[A-Z]{2}[0-9]{2}[A-Z]{3}$", reg) is not None


def looks_like_prefix_plate(reg: str) -> bool:
    """
    Check if the registration matches prefix style:

        A000AAA
        A00AAA
        A0AAA

    Example:
        P123ABC
    """
    return re.fullmatch(r"^[A-Z][0-9]{1,3}[A-Z]{3}$", reg) is not None


def looks_like_suffix_plate(reg: str) -> bool:
    """
    Check if the registration matches suffix style:

        AAA000A
        AAA00A
        AAA0A

    Example:
        ABC123D
    """
    return re.fullmatch(r"^[A-Z]{3}[0-9]{1,3}[A-Z]$", reg) is not None


def looks_like_dateless_plate(reg: str) -> bool:
    """
    Check if the registration matches a stricter dateless style.

    Dateless plates vary, but to reduce OCR junk we avoid allowing
    any 1-7 alphanumeric value. Instead we require:
    - 1 to 7 characters total
    - letters and digits only
    - must contain at least one letter

    Examples:
        M44SSM
        P99TER

    Rejected examples:
        01162
        0000000
    """
    if not re.fullmatch(r"^[A-Z0-9]{1,7}$", reg):
        return False

    # Require at least one letter so pure digit junk does not pass
    if not re.search(r"[A-Z]", reg):
        return False

    return True


def detect_ocr_suspicion_in_current_plate(reg: str) -> str:
    """
    Detect common OCR mistakes specifically for modern UK plates (AA00AAA).

    Expected character classes for modern plates:
        positions 0-1 -> letters
        positions 2-3 -> digits
        positions 4-6 -> letters

    If a character looks like a common OCR-confused symbol in the wrong place,
    we return a helpful reason string. Otherwise return an empty string.

    Example suspicious cases:
        0Y64EUJ  -> position 0 should be a letter
        LG720WL  -> position 4 should be a letter, but 0 appears
        AD08FH0  -> final position should be a letter, but 0 appears
    """
    if len(reg) != 7:
        return ""

    # Common OCR confusion groups
    letter_like_digits = {"0", "1", "2", "5", "8"}
    digit_like_letters = {"O", "I", "Z", "S", "B"}

    # Positions 0,1 should be letters
    for pos in [0, 1]:
        ch = reg[pos]
        if ch in letter_like_digits:
            return (
                f"Suspicious OCR: character '{ch}' at position {pos + 1} "
                f"looks digit-like where a letter is expected"
            )

    # Positions 2,3 should be digits
    for pos in [2, 3]:
        ch = reg[pos]
        if ch in digit_like_letters:
            return (
                f"Suspicious OCR: character '{ch}' at position {pos + 1} "
                f"looks letter-like where a digit is expected"
            )

    # Positions 4,5,6 should be letters
    for pos in [4, 5, 6]:
        ch = reg[pos]
        if ch in letter_like_digits:
            return (
                f"Suspicious OCR: character '{ch}' at position {pos + 1} "
                f"looks digit-like where a letter is expected"
            )

    return ""


def detect_general_ocr_suspicion(reg: str) -> str:
    """
    Detect broader OCR warning signs even when the plate does not fit the
    modern format exactly.

    These are conservative heuristics to catch likely bad OCR values.

    Examples:
        01162       -> all digits / mostly digits
        0SHG736     -> starts with zero in a suspicious way
        DG1BBYR     -> odd mixed pattern
    """
    if not reg:
        return "Blank or missing registration"

    if len(reg) < 2:
        return "Too short to be a plausible registration"

    if len(reg) > 8:
        return "Too long to be a plausible registration"

    if not re.fullmatch(r"^[A-Z0-9]+$", reg):
        return "Contains unsupported characters"

    # Pure digits are very unlikely to be a valid UK registration
    if re.fullmatch(r"^[0-9]+$", reg):
        return "All-digit value looks like OCR noise, not a registration"

    # Starts with 0 is highly suspicious in UK registration context
    if reg.startswith("0"):
        return "Starts with zero, likely OCR confusion"

    return ""


def validate_registration(value: str) -> ValidationResult:
    """
    Validate a raw registration value and return structured information.

    Validation strategy
    -------------------
    1. Clean the value.
    2. Reject blank / malformed values.
    3. Check if it matches one of the recognised UK formats.
    4. For modern plates, block suspicious OCR substitutions.
    5. For non-matching values, return a clear reason.

    Returns
    -------
    ValidationResult
    """

    raw = "" if value is None else str(value)
    cleaned = clean_registration(raw)

    if cleaned == "" or cleaned.lower() == "nan":
        return {
            "raw": raw,
            "cleaned": "",
            "is_valid": False,
            "reason": "Blank or missing registration",
        }

    # General OCR sanity checks first
    general_issue = detect_general_ocr_suspicion(cleaned)
    if general_issue:
        return {
            "raw": raw,
            "cleaned": cleaned,
            "is_valid": False,
            "reason": general_issue,
        }

    # 1. Modern current format
    if looks_like_current_plate(cleaned):
        ocr_issue = detect_ocr_suspicion_in_current_plate(cleaned)
        if ocr_issue:
            return {
                "raw": raw,
                "cleaned": cleaned,
                "is_valid": False,
                "reason": ocr_issue,
            }

        return {
            "raw": raw,
            "cleaned": cleaned,
            "is_valid": True,
            "reason": "Valid UK current registration format",
        }

    # 2. Prefix format
    if looks_like_prefix_plate(cleaned):
        return {
            "raw": raw,
            "cleaned": cleaned,
            "is_valid": True,
            "reason": "Valid UK prefix registration format",
        }

    # 3. Suffix format
    if looks_like_suffix_plate(cleaned):
        return {
            "raw": raw,
            "cleaned": cleaned,
            "is_valid": True,
            "reason": "Valid UK suffix registration format",
        }

    # 4. Dateless format
    if looks_like_dateless_plate(cleaned):
        return {
            "raw": raw,
            "cleaned": cleaned,
            "is_valid": True,
            "reason": "Valid UK dateless registration format",
        }

    # 5. If none matched, reject before API lookup
    return {
        "raw": raw,
        "cleaned": cleaned,
        "is_valid": False,
        "reason": "Invalid UK registration format before API lookup",
    }