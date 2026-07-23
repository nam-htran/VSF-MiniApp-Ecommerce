"""What a shop may not list.

Vingroup's review rules forbid a marketplace from carrying certain goods,
and the platform holds the app responsible for what its sellers post. This
is the crude first gate: a keyword list applied when a product is created
or edited, so obviously prohibited listings never reach the storefront.

It is deliberately blunt and deliberately server-side. A real marketplace
adds image scanning, reports and human review on top; none of that changes
the fact that the check cannot live in the seller's own app, where it would
simply be skipped.

Matching is accent- and case-insensitive, because "thuốc lá", "THUOC LA"
and "thuoc-la" are the same listing to everyone except a naive `in`.
"""

import re
import unicodedata

# Grouped by why they are here, so the list can be argued with rather than
# just obeyed.
BANNED_TERMS = {
    # Weapons and explosives. Note what is *not* here: bare "sung". In a
    # syllable-separated language a one-syllable term is a false-positive
    # machine — it would block "kẹo sung sướng" and "quả sung". Terms need
    # at least two syllables to be safe to match on.
    "sung ngan", "sung san", "dan duoc", "thuoc no", "vu khi", "luu dan",
    # Drugs and controlled substances
    "ma tuy", "heroin", "cocaine", "can sa", "thuoc lac", "bong cuoi",
    # Tobacco and vaping
    "thuoc la", "xi ga", "vape", "pod thuoc",
    # Wildlife
    "nga voi", "sung te giac", "vay te te", "mat gau",
    # Counterfeits and stolen goods
    "hang gia", "hang nhai", "sieu fake", "do an cap",
    # Documents and credentials
    "bang gia", "giay to gia", "cmnd gia", "con dau gia",
    # Adult and gambling
    "do choi nguoi lon", "phim sex", "ca do", "ca cuoc",
}


def _fold(text: str) -> str:
    """Strip accents, punctuation and case so variants collapse together."""
    stripped = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    # đ has no combining form, so it survives the pass above.
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def banned_terms_in(*fields: str | None) -> list[str]:
    """Every prohibited term found across the given text, in list order.

    Returns the matches rather than a bool so the seller is told which word
    is the problem — "sản phẩm bị từ chối" with no reason is a support
    ticket waiting to happen.
    """
    haystack = f" {_fold(' '.join(f for f in fields if f))} "
    found = []
    for term in BANNED_TERMS:
        # Padded so "sung" matches the word, not "sung sướng" or "khung".
        if f" {term} " in haystack:
            found.append(term)
    return sorted(found)
