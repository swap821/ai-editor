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
                f"contains an unrepresentable word ({self.detail!r}); mixing "
                "ASCII and non-ASCII letters inside one word is a homoglyph "
                "signature, not ordinary multilingual text"
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


#: Categories with no visible glyph: format controls (ZWSP, ZWNJ, ZWJ, BOM,
#: soft hyphen, the tag block), C0/C1 controls (CR, LF, TAB), private-use and
#: surrogates. What to DO with them is the subtle part -- see below.
_INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc", "Co", "Cs"})


def _strip_invisibles_and_marks(text: str, *, invisibles_as_space: bool) -> str:
    """Decompose *text* and drop combining marks, reading invisibles two ways.

    Invisible characters cannot be handled correctly by a single rule, and the
    second red-team campaign proved it by exploiting both directions:

    * Deleting them lets ``self<CR><LF>approve`` collapse to ``selfapprove`` --
      one token, so the two-token marker ``self approve`` stops matching.
    * Spacing them lets ``appr<ZWSP>ove`` split into ``appr ove`` -- two tokens,
      so the one-token marker ``approve`` stops matching.

    Either rule alone is a bypass. Guessing which reading the attacker intended
    is the mistake. This produces both, and `screen_text` refuses if either one
    hits -- which is cheap, and fail-closed by construction.

    Combining marks are dropped after NFKD so "a" + U+0301 and the precomposed
    "á" reduce identically.
    """
    replacement = " " if invisibles_as_space else ""
    rebuilt = "".join(
        replacement if unicodedata.category(char) in _INVISIBLE_CATEGORIES else char
        for char in text
    )
    decomposed = unicodedata.normalize("NFKD", rebuilt)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@lru_cache(maxsize=4096)
def normalise_for_screening(text: str, invisibles_as_space: bool = False) -> str:
    """Fold *text* to the canonical form the marker lists are matched against.

    Returns a space-delimited token string: lowercase ASCII words separated by
    single spaces, with every punctuation and spacing difference erased.

    Note the failure mode this deliberately no longer relies on. The final step
    maps anything outside ``[0-9a-z]`` to a space, so an unmappable letter
    *splits the word it sits in* -- ``bypɑss`` becomes ``byp ss``, and the
    marker is destroyed rather than matched. That is a fail-OPEN transform.
    It is why `obfuscated_tokens` must catch such characters independently,
    before this function's output is ever consulted. Normalisation cannot be
    made complete; refusing what it cannot represent is what makes it safe.
    """
    stripped = _strip_invisibles_and_marks(
        text, invisibles_as_space=invisibles_as_space
    )
    folded = "".join(_CONFUSABLES.get(char, char) for char in stripped.casefold())
    de_leet = _LEET_IN_WORD.sub(lambda m: _LEET[m.group(1)], folded)
    return " ".join(_NON_WORD.sub(" ", de_leet).split())


_ALNUM_RUN = re.compile(r"[^\W_]+", re.UNICODE)


def _splits_under_normalisation(word: str) -> bool:
    """True when normalising *word* breaks one run of letters into several.

    The direct signature of the fail-open mechanism, independent of *which*
    character caused it. Found by the generalisation sweep in the regression
    corpus, which is the only reason it exists: the ASCII-mixing rule above
    closed 328 of the 330 Latin-named lookalikes and silently left two.

    ``Ŀ``/``ŀ`` (U+013F/U+0140, L WITH MIDDLE DOT) decompose under NFKD to
    ``L`` + U+00B7 MIDDLE DOT. The dot is punctuation, not a combining mark, so
    it survives the mark-strip and is then treated as a separator -- ``bypŀss``
    becomes ``bypl ss``. Every letter left behind is ASCII, so nothing above
    fires, and the marker is destroyed exactly as before.

    Only runs containing at least one ASCII letter are checked. A wholly
    non-Latin word legitimately loses characters it has no ASCII spelling for
    (``языке`` -> ``k e``), and flagging that would refuse ordinary Russian
    rather than an attack. The signature is an intruder inside an otherwise
    ASCII word.
    """
    for run in _ALNUM_RUN.findall(word):
        if not any(char.isascii() and char.isalpha() for char in run):
            continue
        if len(normalise_for_screening(run).split()) > 1:
            return True
    return False


def obfuscated_tokens(text: str) -> tuple[str, ...]:
    """Words in *text* whose spelling this screen cannot faithfully represent.

    The generic defence -- the one that has to hold when `_CONFUSABLES` is
    incomplete, which it permanently is. Two independent signatures:

    **1. ASCII letters mixed with non-ASCII letters inside one word.** This is
    the rule that carries the weight. ``bypɑss`` (U+0251 LATIN SMALL LETTER
    ALPHA) and ``ɡrant`` (U+0261 LATIN SMALL LETTER SCRIPT G) are visually
    identical to ``bypass`` and ``grant``, absent from `_CONFUSABLES``, and --
    this is what the first version got wrong -- Unicode *names* them "LATIN
    SMALL LETTER ...". They are IPA Extensions. A script-name check sees one
    script and waves them through, which is how the second red-team campaign
    walked the entire organ end to end.

    Mixing representable and unrepresentable letters inside one word has no
    legitimate reading, so it is refused without consulting any marker list.
    Checked *before* confusable folding, against the casefolded/NFKD form:

    * ``café`` -> ``cafe`` and ``Straße`` -> ``strasse`` are pure ASCII: clean.
    * ``комментарий`` is wholly non-ASCII: clean. Ordinary multilingual text is
      single-representation; the signature is the *mixing*, not the foreignness.
    * ``mоdel`` (Cyrillic о) and ``bypɑss`` (Latin-named alpha) both mix, and
      the second is caught without anyone having enumerated U+0251.

    **2. Two different scripts inside one word** -- the original rule, kept
    because it still catches an all-non-ASCII word built from two scripts.

    Both invisible-character readings are examined, so a word cannot hide by
    being split or merged by a zero-width or control character.
    """
    offenders: list[str] = []
    for as_space in (False, True):
        cleaned = _strip_invisibles_and_marks(text, invisibles_as_space=as_space)
        for word in cleaned.casefold().split():
            letters = [char for char in word if char.isalpha()]
            if not letters:
                continue
            # Fold KNOWN confusables before asking whether the word mixes
            # representable and unrepresentable letters. Without this, any
            # mapped letter that does not NFKD-decompose still counts as
            # non-ASCII here and the word is refused even though the screen
            # can spell it perfectly well.
            #
            # The third red-team campaign found that as a false positive on
            # ordinary Polish: "Paweł" and "Łódź" contain U+0142, which IS in
            # _CONFUSABLES (-> "l") but has no decomposition, so a legitimate
            # amendment naming a Polish operator or city was refused -- and
            # refused by _touches_foundation_law, which sits inside
            # ratify_amendment, so a valid capability could not save it.
            #
            # Security is unchanged: a letter the map cannot fold is still
            # non-ASCII after folding and is still refused. This narrows the
            # rule to exactly its intent -- letters this screen CANNOT
            # represent, not letters that merely started out non-ASCII.
            # A word with no ASCII letters at all is ordinary multilingual
            # text -- Russian, Greek, Armenian -- and is never the signature.
            # This is decided on the ORIGINAL letters, because folding turns
            # some Cyrillic into ASCII and would otherwise make every Russian
            # word look like a mixed one.
            if not any(char.isascii() for char in letters):
                continue
            folded = [_CONFUSABLES.get(char, char) for char in letters]
            ascii_letters = [char for char in folded if char.isascii()]
            if ascii_letters and len(ascii_letters) != len(folded):
                offenders.append(word)
                continue
            scripts = {script for script in map(_script_of, letters) if script}
            if len(scripts) > 1 and "LATIN" in scripts:
                offenders.append(word)

    # Checked against the RAW words, not the cleaned ones. The split this looks
    # for is performed by NFKD inside `_strip_invisibles_and_marks`, so by the
    # time a word reaches the loop above the evidence has already been consumed:
    # `bypŀss` arrives as `bypl·ss`, whose alphanumeric runs are `bypl` and `ss`,
    # each of which normalises cleanly. Ask the original.
    for word in text.split():
        if _splits_under_normalisation(word):
            offenders.append(word)
    return tuple(dict.fromkeys(offenders))


@lru_cache(maxsize=4096)
def _marker_tokens(marker: str) -> str:
    return f" {normalise_for_screening(marker)} "


def _haystacks(text: str) -> tuple[str, ...]:
    """Both invisible-character readings of *text*, space-padded for matching.

    Deduplicated: for text containing no invisible characters -- the normal
    case -- both readings are identical and only one is searched.
    """
    readings = {
        f" {normalise_for_screening(text, as_space)} " for as_space in (False, True)
    }
    return tuple(readings)


def marker_hit(text: str, markers: tuple[str, ...]) -> str | None:
    """First marker in *markers* present in *text*, or None.

    Matches on whole-word boundaries, so the marker "self approve" does not
    fire inside "myself approves". Returns the marker as written in the source
    list, so error messages name the rule and never echo the attacker's text.

    Searches both invisible-character readings: ``self<CR><LF>approve`` and
    ``appr<ZWSP>ove`` are each a bypass of one reading and caught by the other.
    """
    haystacks = _haystacks(text)
    return next(
        (
            marker
            for marker in markers
            if any(_marker_tokens(marker) in hay for hay in haystacks)
        ),
        None,
    )


def cooccurrence_hit(
    text: str, activation: tuple[str, ...], deferred: tuple[str, ...]
) -> tuple[str, str] | None:
    """First (activation, deferred-notice) marker pair present in *text*.

    Order-independent, and that is the whole point of this revision.

    The previous version required the activation marker to appear *earlier in
    the string* than the notification marker, on the theory that "apply the
    change, then notify the operator" is an attack while "revert the change,
    then notify the operator" is a correct rollback plan. The second red-team
    campaign destroyed that premise with ordinary English:

        "Notify the operator, but only after you apply the change."
        "Step 2: Notify the operator.  Step 1: Apply the change."

    Both describe activation-before-notification while placing the notification
    phrase first. Textual order and described order are independent in English,
    and matching on string position while claiming to detect sequence was a
    screen that looked smarter than it was.

    So the signal is now mere co-occurrence: an amendment proposal that names
    both an activation and a deferred notification is refused regardless of
    arrangement. This over-refuses text like "apply the change once the
    operator approves, then notify the team" -- deliberately. Re-wording a
    legitimate proposal costs a minute; the miss costs the constitution, and
    the campaign showed the miss is easy to arrange and hard to see.
    """
    hit_activation = marker_hit(text, activation)
    if hit_activation is None:
        return None
    hit_deferred = marker_hit(text, deferred)
    if hit_deferred is None:
        return None
    return hit_activation, hit_deferred


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
    "cooccurrence_hit",
    "marker_hit",
    "normalise_for_screening",
    "obfuscated_tokens",
    "screen_text",
]
