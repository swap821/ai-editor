"""Unicode-hardened text screening for the governance keyword guards.

Why this module exists
----------------------
Three governance controls decided whether text was dangerous by lowercasing
it and asking ``marker in text``:

* ``constitutional_learning.assert_never_reduces_human_authority`` -- the one
  rule organ 46 exists to serve (Laws I / III / XIII).
* ``adversarial_simulations._marker_hit`` -- the textual half of all 9 named
  adversarial simulations.
* ``amendment_authority._touches_foundation_law`` -- the guard that makes the
  six foundation laws unamendable in v1, and which runs *inside*
  ``ratify_amendment`` rather than as a pre-screen.

A multi-agent red-team campaign against organ 46 (2026-08-08, 27 agents)
defeated all three with a one-line string transform. Measured, not argued:

    plain ASCII                        -> refused
    Cyrillic homoglyph ('a' -> U+0430) -> passed
    zero-width space inside a word     -> passed
    NFKD + combining mark              -> passed
    full-width characters              -> passed

Raw substring matching compares codepoints. An attacker rewrites the
codepoints and keeps the glyphs, so a human reviewer reads the forbidden
sentence and the machine reads nothing at all. That is the worst possible
failure mode for a screen whose entire job is to be read by both.

The two defences here
---------------------
**1. Normalisation** (`normalise_for_screening`). Fold away every difference
that does not change what a human sees: invisible format characters,
compatibility forms, combining marks, an explicit confusables map, case, and
punctuation/spacing. Markers are folded through the identical pipeline, so
"auto-approve", "auto approve", "auto_approve" and "аutо‑аpprоve" all reduce
to one token sequence.

**2. Mixed-script detection** (`obfuscated_tokens`). Normalisation can only
fold confusables someone thought to enumerate, and that list will always be
incomplete -- Unicode has thousands of candidates and gains more each
release. So there is a second, generic signature that does not depend on the
map being complete: a single *word* that mixes Latin letters with letters
from another script. ``sеlf-approve`` (Cyrillic е) is mixed-script whether or
not U+0435 is in the map. This is the same rule browsers use against IDN
spoofing, and it is the load-bearing defence -- the map is only an
optimisation on top of it.

A word written *entirely* in another script is not flagged: that is ordinary
multilingual text, not a homoglyph attack. The signature is the mixing.

Deliberate design choices
-------------------------
*Over-matching is the safe direction.* A false positive refuses a legitimate
proposal, which costs availability. A false negative lets a proposal that
reads as "the model may approve its own amendments" through a guard whose
name promises it cannot. These are not symmetric, so every judgement call
below leans toward refusing.

*Zero-width characters are normalised away, not refused on sight.* They are
neutralised by step 1, so an attack that uses them is caught by the marker
match itself. Refusing merely for their presence would reject honest text
pasted out of a browser or a PDF, for no additional security.

*Digit folding is scoped to letters-inside-a-word.* ``appr0ve`` folds;
``Article 1`` and ``policy-v1`` do not. Leetspeak is pure ASCII, so
mixed-script detection cannot see it and normalisation must.

The honest limit
----------------
This closes *mechanical* evasion -- rewriting the encoding of a sentence
whose meaning is unchanged. It does nothing about *semantic* evasion:
"ratification is deemed complete if the operator does not respond within 72
hours" contains no marker in any encoding, and no keyword list can be made
complete against paraphrase. Marker screening is a floor, and the structural
control is elsewhere and unaffected: ``ratify_amendment`` requires a real,
already-consumed capability bound to a human operator, which no model or
worker can produce. See ``adversarial_simulations`` for the semantic marker
families added alongside this module, and for what they still cannot catch.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

#: Explicit, auditable confusables map: visually-Latin characters drawn from
#: other scripts, folded to the ASCII letter they impersonate. Hand-authored
#: rather than pulled from a dependency so a reviewer can read the whole
#: threat surface in one screen. Incompleteness here is expected and is why
#: `obfuscated_tokens` exists -- this map is a convenience, not the control.
#:
#: Uppercase forms are absent on purpose: `casefold()` runs first.
_CONFUSABLES: dict[str, str] = {
    # --- Cyrillic ---
    "а": "a",  # а
    "в": "b",  # в
    "г": "r",  # г
    "е": "e",  # е
    "к": "k",  # к
    "м": "m",  # м
    "н": "h",  # н
    "о": "o",  # о
    "п": "n",  # п
    "р": "p",  # р
    "с": "c",  # с
    "т": "t",  # т
    "у": "y",  # у
    "х": "x",  # х
    "ё": "e",  # ё
    "ѕ": "s",  # ѕ
    "і": "i",  # і
    "ј": "j",  # ј
    "ѵ": "v",  # ѵ
    "һ": "h",  # һ
    "ӏ": "l",  # ӏ
    "ԁ": "d",  # ԁ
    "ԛ": "q",  # ԛ
    "ԝ": "w",  # ԝ
    # --- Greek ---
    "α": "a",  # α
    "β": "b",  # β
    "γ": "y",  # γ
    "ε": "e",  # ε
    "η": "n",  # η
    "ι": "i",  # ι
    "κ": "k",  # κ
    "μ": "u",  # μ
    "ν": "v",  # ν
    "ο": "o",  # ο
    "ρ": "p",  # ρ
    "ς": "c",  # ς
    "τ": "t",  # τ
    "υ": "u",  # υ
    "χ": "x",  # χ
    "ω": "w",  # ω
    "ϱ": "p",  # ϱ
    "ϲ": "c",  # ϲ
    "ϳ": "j",  # ϳ
    # --- Armenian ---
    "գ": "q",  # գ
    "հ": "h",  # հ
    "յ": "j",  # յ
    "ո": "n",  # ո
    "ս": "u",  # ս
    "ր": "r",  # ր
    "օ": "o",  # օ
    # --- Latin letters that impersonate other Latin letters ---
    "đ": "d",  # đ
    "ħ": "h",  # ħ
    "ı": "i",  # ı
    "ł": "l",  # ł
    "ŧ": "t",  # ŧ
    "ø": "o",  # ø
    "ȷ": "j",  # ȷ
    # --- small capitals ---
    "ᴀ": "a",
    "ʙ": "b",
    "ᴄ": "c",
    "ᴅ": "d",
    "ᴇ": "e",
    "ɢ": "g",
    "ʜ": "h",
    "ɪ": "i",
    "ᴊ": "j",
    "ᴋ": "k",
    "ʟ": "l",
    "ᴍ": "m",
    "ɴ": "n",
    "ᴏ": "o",
    "ᴘ": "p",
    "ʀ": "r",
    "ᴛ": "t",
    "ᴜ": "u",
    "ᴠ": "v",
    "ᴡ": "w",
    "ʏ": "y",
    "ᴢ": "z",
}

#: Leetspeak substitutions, applied only to a digit that sits *between* two
#: letters of the same word (`appr0ve` yes, `Article 1` and `v1` no).
_LEET: dict[str, str] = {
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
}

_LEET_IN_WORD = re.compile(r"(?<=[^\W\d_])([013457])(?=[^\W\d_])", re.UNICODE)
_NON_WORD = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True)
class ScreeningHit:
    """Why a piece of text was refused.

    ``kind`` is ``"marker"`` when a forbidden phrase was matched (``detail``
    is the marker as written in the source list, not the attacker's spelling
    of it), or ``"obfuscation"`` when a word mixed scripts (``detail`` is the
    offending word).
    """

    kind: str
    detail: str

    def describe(self, marker_noun: str = "a marker") -> str:
        """A caller-flavoured reason phrase, beginning with "contains".

        *marker_noun* lets each screen name its own rule ("an approval-bypass
        marker") so the message says which control refused, not merely that
        something did. The obfuscation reason ignores it: a mixed-script word
        is refused on its own signature, before any marker list is consulted,
        so naming one would misreport why.
        """
        if self.kind == "obfuscation":
            return (
                f"contains a mixed-script word ({self.detail!r}); characters "
                "from two scripts inside one word is a homoglyph signature, "
                "not ordinary multilingual text"
            )
        return f"contains {marker_noun} ({self.detail!r})"


def _script_of(char: str) -> str | None:
    """Coarse script name for a letter, or None when *char* is not a letter.

    Derived from the character's own Unicode name ("CYRILLIC SMALL LETTER A"
    -> "CYRILLIC") rather than a hand-maintained codepoint-range table, so it
    stays correct for scripts nobody here thought about.
    """
    if not char.isalpha():
        return None
    try:
        return unicodedata.name(char).split(" ", 1)[0]
    except ValueError:  # unnamed codepoint -- treat as its own script
        return "UNNAMED"


def _strip_invisibles_and_marks(text: str) -> str:
    """Remove format characters, then decompose and drop combining marks.

    Order matters. Format characters (Cf: ZWSP, ZWNJ, ZWJ, BOM, soft hyphen,
    the tag block) are *deleted* so the letters they were inserted between
    rejoin into a word. Combining marks are dropped after NFKD so that
    "a" + U+0301 and the precomposed "á" reduce identically.
    """
    without_format = "".join(
        char
        for char in text
        if unicodedata.category(char) not in {"Cf", "Cc", "Co", "Cs"}
    )
    decomposed = unicodedata.normalize("NFKD", without_format)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@lru_cache(maxsize=4096)
def normalise_for_screening(text: str) -> str:
    """Fold *text* to the canonical form the marker lists are matched against.

    Returns a space-delimited token string: lowercase ASCII words separated
    by single spaces, with every punctuation and spacing difference erased.
    Two texts that a human would read as the same sentence normalise to the
    same string.
    """
    stripped = _strip_invisibles_and_marks(text)
    folded = "".join(_CONFUSABLES.get(char, char) for char in stripped.casefold())
    de_leet = _LEET_IN_WORD.sub(lambda m: _LEET[m.group(1)], folded)
    return " ".join(_NON_WORD.sub(" ", de_leet).split())


def obfuscated_tokens(text: str) -> tuple[str, ...]:
    """Words in *text* that mix Latin letters with another script.

    The generic homoglyph signature. Independent of `_CONFUSABLES`: it fires
    on any script-mixing word, including ones built from confusables nobody
    has enumerated yet. A word written wholly in one non-Latin script is not
    flagged -- that is multilingual text, not an attack.
    """
    cleaned = _strip_invisibles_and_marks(text)
    offenders: list[str] = []
    for word in re.split(r"[\s ]+", cleaned):
        scripts = {
            script
            for script in (_script_of(char) for char in word)
            if script is not None
        }
        if len(scripts) > 1 and "LATIN" in scripts:
            offenders.append(word)
    return tuple(offenders)


@lru_cache(maxsize=4096)
def _marker_tokens(marker: str) -> str:
    return f" {normalise_for_screening(marker)} "


def marker_hit(text: str, markers: tuple[str, ...]) -> str | None:
    """First marker in *markers* present in *text*, or None.

    Matches on whole-word boundaries: the marker "self approve" does not fire
    inside "myself approves". Returns the marker as written in the source
    list so error messages name the rule, never the attacker's text.
    """
    haystack = f" {normalise_for_screening(text)} "
    return next(
        (marker for marker in markers if _marker_tokens(marker) in haystack), None
    )


def ordered_pair_hit(
    text: str, earlier: tuple[str, ...], later: tuple[str, ...]
) -> tuple[str, str] | None:
    """First (earlier, later) marker pair that appears in *that order*.

    Some attacks are only visible as a sequence. "Apply the change, then
    notify the operator" reduces human authority to a receipt; "revert the
    change, then notify the operator" is a correct rollback plan. The
    distinguishing signal is not either phrase -- it is that an *activation*
    precedes the notification.

    A flat marker list cannot express that, and the version of this screen
    that tried produced either a bypass or a refusal of ordinary text.
    """
    haystack = f" {normalise_for_screening(text)} "
    for first in earlier:
        start = haystack.find(_marker_tokens(first))
        if start < 0:
            continue
        tail = haystack[start:]
        for second in later:
            if _marker_tokens(second) in tail:
                return first, second
    return None


def screen_text(text: str, markers: tuple[str, ...]) -> ScreeningHit | None:
    """Refuse *text* on either signature: a forbidden marker, or obfuscation.

    Obfuscation is checked first and refuses on its own. A mixed-script word
    in a governance proposal has no legitimate reading, and refusing it
    without needing to know which marker it was hiding is what keeps this
    screen honest when `_CONFUSABLES` is incomplete -- which it permanently
    is.
    """
    offenders = obfuscated_tokens(text)
    if offenders:
        return ScreeningHit(kind="obfuscation", detail=offenders[0])
    hit = marker_hit(text, markers)
    if hit is not None:
        return ScreeningHit(kind="marker", detail=hit)
    return None


__all__ = [
    "ScreeningHit",
    "marker_hit",
    "normalise_for_screening",
    "obfuscated_tokens",
    "ordered_pair_hit",
    "screen_text",
]
