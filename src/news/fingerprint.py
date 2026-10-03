"""Canonicalisation, fingerprinting and similarity for news deduplication.

Three escalating levels of "have I seen this before?":

1. ``canonical_url``  - the same article behind tracking parameters.
2. ``story_key``      - the same *event* reported by different outlets.

A URL match is certain. A story-key match is a judgement call, so the
thresholds here are deliberately conservative: merging two genuinely
different events is worse than analysing both and sending the stronger one,
because a wrong merge silently hides news.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that identify the *page*, not the *article*.
_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "gbraid", "wbraid", "mc_", "igshid")
_TRACKING_KEYS = {
    "ref", "referrer", "source", "src", "cmp", "campaign", "sh", "share",
    "amp", "output", "feature", "ncid", "cid", "smid", "at_medium", "ns_campaign",
}

# Outlets that serve the same story under a different slug shape.
_CANONICAL_HOST_ALIASES = {
    "m.economictimes.indiatimes.com": "economictimes.indiatimes.com",
    "economictimes.indiatimes.com": "economictimes.indiatimes.com",
    "www.livemint.com": "livemint.com",
    "livemint.com": "livemint.com",
    "www.moneycontrol.com": "moneycontrol.com",
    "moneycontrol.com": "moneycontrol.com",
    "www.business-standard.com": "business-standard.com",
    "business-standard.com": "business-standard.com",
    "www.thehindubusinessline.com": "thehindubusinessline.com",
    "thehindubusinessline.com": "thehindubusinessline.com",
    "www.financialexpress.com": "financialexpress.com",
    "financialexpress.com": "financialexpress.com",
}

# Boilerplate that carries no event information. Removed before fingerprinting
# so "Breaking: X wins order" and "X wins order, says report" collide.
_BOILERPLATE = [
    "breaking", "exclusive", "update", "updated", "live", "video", "watch",
    "news", "latest", "breakingnews", "just in", "developing story",
    "pti", "iANS", "ians", "reuters", "agency", "firstpost", "business standard",
    "the hindu business line", "livemint", "moneycontrol", "financial express",
    "economictimes", "the economic times", "times of india", "mint",
    "says", "report", "reports", "reported", "sources", "source",
    "here is why", "what is", "explained", "full list", "top news",
]

# Tokens that carry the event itself. Used for the "new development" test.
_DEVELOPMENT_TOKENS = {
    "approves", "approved", "approval", "rejects", "rejected", "rejects",
    "orders", "ordered", "directs", "directed", "penalises", "penalises",
    "penalty", "fine", "fined", "notice", "notices", "warns", "warned",
    "launches", "launched", "unveils", "unveiled", "wins", "won", "bags",
    "bags", "secures", "secured", "signs", "signed", "files", "filed",
    "acquires", "acquisition", "merger", "demerger", "stake", "sells",
    "divests", "raises", "raises", "funding", "raises", "qip", "fpo", "ipo",
    "resigns", "resignation", "appoints", "appointed", "steps", "stepsdown",
    "downgrade", "upgrade", "rating", "downgrades", "upgrades", "default",
    "bankrupt", "insolvency", "probe", "investigation", "raid", "search",
    "wins", "record", "highest", "lowest", "guidance", "profit", "loss",
    "revenue", "earnings", "results", "dividend", "buyback", "bonus",
    "contract", "order", "orders", "deal", "partnership", "expansion",
    "investment", "capex", "plant", "facility", "approval", "ban", "bans",
    "restricted", "suspends", "suspended", "resumes", "resumed", "strike",
    "layoff", "shutdown", "opens", "commissions", "tender", "cancellation",
}

_WORD_RE = re.compile(r"[a-z0-9]+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")

# Indian numbering: 10,000 crore == 10000 crore. Keeps "invests Rs 10,000 crore"
# and "invests Rs 10000 crore" in the same bucket.
_NUM_RE = re.compile(r"(\d)[,](\d)")


def normalise_numbers(text: str) -> str:
    """Collapse Indian/English digit grouping so 10,000 == 10000."""
    prev = None
    out = text
    while prev != out:
        prev = out
        out = _NUM_RE.sub(r"\1\2", out)
    return out


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def canonical_url(url: str) -> str:
    """Reduce a URL to a stable identity.

    Lowercases scheme/host, drops ``www.``, strips tracking parameters and
    fragments, and removes a trailing slash. AMP suffixes (``/amp``) are kept
    because a separate AMP page is a separate fetch, not a separate story.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    host = _CANONICAL_HOST_ALIASES.get(host, host)

    kept = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        low = key.lower()
        if low in _TRACKING_KEYS or low.startswith(_TRACKING_PREFIXES):
            continue
        kept.append((key, value))
    kept.sort()
    query = urlencode(kept)

    path = _NON_WORD_RE.sub("", parts.path).lower()
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, host, path, query, ""))


def normalise_title(title: str) -> str:
    """Reduce a headline to comparable tokens.

    Lowercase, de-accent, drop boilerplate prefixes and outlet names, drop
    punctuation, collapse digit grouping. Keeps the first 14 content tokens -
    long enough to distinguish events, short enough to survive rewording.
    """
    if not title:
        return ""
    text = strip_accents(title).lower()
    text = normalise_numbers(text)

    # Drop a leading outlet/label prefix such as "ET Markets:" or "Business".
    text = re.sub(r"^[a-z0-9 .&|]{0,24}:\s*", "", text)

    text = _NON_WORD_RE.sub(" ", text)
    words = [w for w in text.split() if w]
    if not words:
        return ""

    cleaned: List[str] = []
    for word in words:
        if word in _BOILERPLATE:
            continue
        cleaned.append(word)
        if len(cleaned) >= 14:
            break
    return " ".join(cleaned)


def title_fingerprint(title: str) -> str:
    """Stable hash of the normalised headline."""
    return hashlib.sha1(normalise_title(title).encode("utf-8")).hexdigest()[:16]


def content_fingerprint(text: str) -> str:
    """Stable hash of a content excerpt, used as a secondary identity check."""
    if not text:
        return ""
    body = _WS_RE.sub(" ", _NON_WORD_RE.sub(" ", strip_accents(text).lower())).strip()
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def content_tokens(text: str, limit: int = 200) -> List[str]:
    body = normalise_numbers(strip_accents(text or "").lower())
    return _WORD_RE.findall(body)[:limit]


def _numbers(text: str) -> List[str]:
    """Material figures (money, percentages) mentioned in a headline."""
    found = re.findall(r"\d+(?:\.\d+)?", normalise_numbers(strip_accents(text or "").lower()))
    return [n for n in found if len(n) >= 2]


def development_tokens(title: str) -> Set[str]:
    """Action words that indicate a *new* development rather than a repeat."""
    words = set(_WORD_RE.findall(strip_accents(title or "").lower()))
    return words & _DEVELOPMENT_TOKENS


def title_similarity(a: str, b: str) -> float:
    """0..1 lexical similarity between two headlines.

    Deliberately not a raw edit-distance ratio. Two headlines can share most
    of their words and still be different events ("board approves dividend"
    vs "board approves Rs 200 crore capex"), while a genuine rewrite can look
    quite different lexically. This blends three signals that fail in
    different places:

    * content-word overlap (catches reordering, which SequenceMatcher punishes)
    * material-figure overlap (catches the same deal reported with new numbers)
    * edit-distance ratio (catches shared phrasing)
    """
    na, nb = normalise_title(a), normalise_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    wa, wb = na.split(), nb.split()
    sa, sb = set(wa), set(wb)
    jaccard = len(sa & sb) / max(1, len(sa | sb))

    seq = SequenceMatcher(None, na, nb).ratio()

    # Material figures: "Rs 500 crore order" and "Rs 10000 crore investment"
    # should not look alike just because both contain a rupee amount.
    na_nums, nb_nums = set(_numbers(a)), set(_numbers(b))
    if not na_nums and not nb_nums:
        figure = 0.5  # neither states a figure: neither for nor against
    elif na_nums and nb_nums:
        overlap = len(na_nums & nb_nums)
        figure = overlap / max(len(na_nums), len(nb_nums))
    else:
        figure = 0.15

    score = 0.45 * jaccard + 0.35 * figure + 0.20 * seq

    # Decisive override: identical material figure + same entity + same kind
    # of event means one story, however differently it is worded. All three
    # are required - the figure alone would merge "Rs 500 crore order" with
    # "Rs 500 crore penalty", and the entity alone would merge two unrelated
    # events from the same company.
    if na_nums and na_nums == nb_nums:
        shares_entity = bool(proper_nouns(a) & proper_nouns(b))
        shares_category = bool(event_categories(a) & event_categories(b))
        if (shares_entity and shares_category) or jaccard >= 0.34:
            score = max(score, 0.80)

    return score


# Event categories. A follow-up about the same *category* is a development;
# two unrelated categories about the same company are two separate stories.
# "Lupin Q2 profit rises" and "Lupin wins a USFDA nod" share a company but not
# a category, so they must never be merged - nor treated as one developing.
_EVENT_CATEGORIES: Dict[str, Set[str]] = {
    "regulatory": {
        "notice", "penalty", "fine", "fined", "sebi", "rbi", "regulator",
        "ban", "bans", "probe", "investigation", "raid", "search", "show",
        "cause", "violation", "breach", "penalise", "penalises", "suspend",
        "suspends", "rescinds", "directions", "adjudication", "tribunal",
        "nclt", "insolvency", "default", "bankrupt", "listing", "delisting",
    },
    "order_contract": {
        "order", "orders", "contract", "contracts", "deal", "deals", "bags",
        "bag", "wins", "win", "won", "award", "awarded", "awards", "tender",
        "signs", "signed", "sign", "agreement", "tieup", "partnership",
        "mandate", "letter", "intent", "loi", "booked", "secures", "secured",
    },
    "earnings": {
        "profit", "loss", "losses", "revenue", "revenues", "earnings",
        "results", "quarter", "quarterly", "margin", "margins", "eps", "pat",
        "q1", "q2", "q3", "q4", "dividend", "buyback", "bonus",
        "guidance", "outlook", "topline", "bottomline", "ebitda", "growth",
    },
    "capex": {
        "capex", "expansion", "plant", "capacity", "facility", "unit",
        "investment", "invest", "invests", "line", "greenfield", "commission",
        "commissions", "inaugurates", "setup", "manufacturing",
    },
    "ma": {
        "acquire", "acquires", "acquisition", "merger", "merge", "demerger",
        "stake", "divest", "divests", "buyout", "takeover", "sell",
    },
    "fundraise": {
        "ipo", "qip", "fpo", "fundraise", "fundraising", "raise", "raises",
        "raised", "debt", "bond", "bonds", "loan", "lending", "ncd",
    },
    "management": {
        "resign", "resigns", "resignation", "appoint", "appoints", "appointed",
        "ceo", "cfo", "md", "chairman", "board", "steps", "down", "quit",
        "quits", "director",
    },
    "product": {
        "launch", "launches", "unveil", "unveils", "unveiled", "introduce",
        "introduces", "reveal", "reveals", "model", "variant",
    },
    "rating": {
        "upgrade", "upgrades", "downgrade", "downgrades", "rating", "ratings",
        "outlook", "moodys", "s&p", "fitch", "crisil", "icra", "care",
    },
    "policy": {
        "rbi", "budget", "policy", "scheme", "subsidy", "plI", "pli",
        "production", "linked", "incentive", "tariff", "customs", "gst",
        "ban", "restriction", "restrictions", "government", "ministry", "cabinet",
        "parliament", "ordinance",
    },
}


def event_categories(title: str) -> Set[str]:
    """Which event categories a headline falls into."""
    words = set(_WORD_RE.findall(strip_accents(title or "").lower()))
    return {name for name, tokens in _EVENT_CATEGORIES.items() if words & tokens}


def is_new_development(
    candidate_title: str,
    prior_headline: str,
    prior_development_fp: str = "",
) -> bool:
    """True when a headline is a *further* development of the same story.

    Three conditions must all hold. All three are needed because any single
    one misfires:

    1. **Same event category.** Without this, "Lupin Q2 profit rises" counts
       as a development of "Lupin wins USFDA nod" purely because both mention
       Lupin and a different rupee figure.
    2. **A new or escalated action** within that category, so a bare rewrite
       ("X wins 500cr order" / "X wins Rs 500 crore order") is not a new
       development.
    3. **New information**: a material figure the prior headline did not
       contain, or an escalation action when the prior headline gave none.
    """
    cand_cats = event_categories(candidate_title)
    prior_cats = event_categories(prior_headline)
    if not cand_cats or not prior_cats or not (cand_cats & prior_cats):
        return False

    cand_dev = development_tokens(candidate_title)
    prior_dev = development_tokens(prior_headline)
    fresh_actions = cand_dev - prior_dev
    if not fresh_actions:
        return False

    cand_nums = set(_numbers(candidate_title))
    prior_nums = set(_numbers(prior_headline))
    new_figures = bool(cand_nums - prior_nums)

    if new_figures:
        return True
    # Escalation without a stated figure: "SEBI notices X" -> "SEBI bans X".
    if not prior_nums and (fresh_actions & _ESCALATION_ACTIONS):
        return True
    return False


_ESCALATION_ACTIONS = {
    "penalty", "fine", "fined", "ban", "bans", "suspended", "suspends",
    "default", "bankrupt", "insolvency", "probe", "investigation", "raid",
    "approves", "approved", "orders", "ordered", "directs", "rescinds",
    "cancels", "cancellation", "downgrade", "downgrades", "resigns",
    "acquires", "acquisition", "demerger", "delisting",
}


def story_key_for(title: str, url: str = "") -> str:
    """Stable identifier for one story instance.

    This is an *identity*, not a semantic hash. Cross-run matching is done by
    :func:`same_story` against stored headlines, because a reworded headline
    will not reproduce a token-based hash and pretending otherwise produces
    duplicate story keys for one event. Using the canonical URL of the chosen
    primary article keeps the key stable, unique and cheap.
    """
    canon = canonical_url(url) if url else ""
    if canon:
        return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:16]
    return title_fingerprint(title)


def topic_tokens(title: str) -> Set[str]:
    """Significant tokens used to decide whether two headlines concern the
    same subject, independent of wording."""
    stop = {
        "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
        "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
        "it", "its", "this", "that", "these", "those", "has", "have", "will",
        "after", "over", "into", "amid", "says", "said", "new", "up", "down",
        "rs", "inr", "crore", "cr", "lakh", "lakhs", "mn", "billion", "million",
        "per", "cent", "pct", "percent", "year", "years", "quarter", "q1", "q2",
        "q3", "q4", "fy", "fy25", "fy26", "may", "june", "july", "aug",
        "company", "ltd", "limited", "india", "indian",
    }
    words = set(_WORD_RE.findall(strip_accents(title or "").lower()))
    return {w for w in words if len(w) > 2 and w not in stop}


def proper_nouns(title: str) -> Set[str]:
    """Capitalised tokens that look like entity names.

    Headlines capitalise names ("Lupin wins...", "SEBI orders..."), so this
    recovers the subject of a sentence even when the only other link between
    two headlines is a corporate word like "Company" that we deliberately
    strip from :func:`topic_tokens`.
    """
    if not title:
        return set()
    common = {
        "the", "a", "an", "and", "or", "but", "if", "of", "in", "on", "at", "to",
        "for", "with", "by", "from", "as", "is", "are", "was", "were", "be",
        "after", "over", "into", "amid", "here", "why", "how", "what", "who",
        "when", "will", "may", "not", "up", "down", "new", "its", "it", "this",
        "that", "these", "those", "has", "have", "had", "rs", "inr", "q1", "q2",
        "q3", "q4", "fy", "i", "we", "you", "he", "she", "they",
    }
    words = strip_accents(title).split()
    out: Set[str] = set()
    for index, raw in enumerate(words):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw)
        if len(cleaned) < 3:
            continue
        low = cleaned.lower()
        if low in common:
            continue
        if cleaned[0].isupper():
            # Skip a capitalised first word: it is usually just sentence case.
            if index == 0 and cleaned.lower() in _FIRST_WORD_OK:
                continue
            out.add(low)
    return out


_FIRST_WORD_OK = {
    "regulator", "company", "government", "ministry", "sebi", "rbi", "nse",
    "bse", "india", "sensex", "nifty", "markets", "market", "stocks", "stock",
    "shares", "share", "brokerage", "brokerages", "report", "reports",
    "shares", "board", "ltd", "limited", "india", "exclusively", "explained",
    "watch", "live", "breaking", "update", "opinion", "analysis", "review",
    "budget", "profit", "loss", "revenue", "results", "q1", "q2", "q3", "q4",
    "why", "how", "what", "here", "top", "best", "list", "stocks",
}


def same_topic(a: str, b: str, min_overlap: int = 1) -> bool:
    """True when two headlines are about the same subject.

    Used only to decide whether a follow-up headline should be attached to an
    existing story as a *development*. Deliberately loose: a false positive
    links two stories under one key (a small loss of de-duplication), while a
    false negative splits one story in two and can re-send it.

    Two independent signals, either sufficient:

    * a proper noun in common ("Lupin", "SEBI", "Infosys")
    * an overlapping distinctive content token
    """
    pn_a, pn_b = proper_nouns(a), proper_nouns(b)
    if pn_a and pn_b and (pn_a & pn_b):
        return True
    ta, tb = topic_tokens(a), topic_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) >= min_overlap


@dataclass(frozen=True)
class MatchResult:
    """Outcome of comparing a candidate article against known history."""

    is_duplicate: bool
    reason: str
    matched_key: str = ""
    is_new_development: bool = False


def same_story(
    candidate_title: str,
    candidate_url: str,
    known_titles: Sequence[Tuple[str, str]],
    *,
    sim_threshold: float = 0.62,
) -> MatchResult:
    """Decide whether ``candidate`` is a repeat of something already known.

    ``known_titles`` is a sequence of ``(key, headline)`` pairs drawn from
    persistent storage - i.e. things already seen on earlier runs.

    Order of checks, cheapest and most certain first:

    1. identical canonical URL        -> certain duplicate
    2. identical normalised headline -> duplicate
    3. composite similarity >= threshold -> duplicate, *unless* the headline
       adds a new development action plus a new material figure, which marks
       a genuine follow-up rather than a rewrite.
    """
    c_canon = canonical_url(candidate_url)

    for key, _known in known_titles:
        if key.startswith("url:") and key[4:] == c_canon:
            return MatchResult(True, "canonical_url_match", key)

    if not c_canon:
        for key, _known in known_titles:
            if key.startswith("url:") and key[4:] == c_canon:
                return MatchResult(True, "canonical_url_match", key)

    cand_fp = title_fingerprint(candidate_title)
    for key, _known in known_titles:
        if key.startswith("title:") and key[6:] == cand_fp:
            return MatchResult(True, "headline_match", key)

    best_key, best_score = "", 0.0
    best_headline = ""
    for key, known_headline in known_titles:
        if key.startswith("url:") or key.startswith("title:"):
            continue
        score = title_similarity(candidate_title, known_headline)
        if score > best_score:
            best_score, best_key, best_headline = score, key, known_headline

    # A follow-up about the same subject counts as a new development even when
    # the wording barely overlaps the original ("X receives notice" ->
    # "SEBI orders X to pay 500 crore"). Checking this before the similarity
    # gate keeps the follow-up attached to the same story instead of orphaning
    # it as an unrelated new key.
    for key, known_headline in known_titles:
        if key.startswith("url:") or key.startswith("title:"):
            continue
        if same_topic(candidate_title, known_headline) and is_new_development(
            candidate_title, known_headline
        ):
            return MatchResult(False, "new_development", key, is_new_development=True)

    if best_score < sim_threshold or not best_key:
        return MatchResult(False, "no_match", "", False)

    return MatchResult(True, f"event_similarity_{best_score:.2f}", best_key)


def known_headline_of(known_titles: Iterable[Tuple[str, str]], key: str) -> str:
    for k, headline in known_titles:
        if k == key:
            return headline
    return ""


def cluster_by_story(
    articles: Sequence["_StoryCandidate"],
    *,
    sim_threshold: float = 0.72,
) -> List[List["_StoryCandidate"]]:
    """Group articles that report the same event.

    Greedy single-pass clustering against the first member of each existing
    cluster. Order-independent enough for a daily batch, and cheap: news
    volumes here are ~100 articles, not ~100k.
    """
    clusters: List[List[_StoryCandidate]] = []
    for article in articles:
        placed = False
        for cluster in clusters:
            head = cluster[0]
            if canonical_url(article.url) and canonical_url(article.url) == canonical_url(head.url):
                cluster.append(article)
                placed = True
                break
            if title_similarity(article.title, head.title) >= sim_threshold:
                cluster.append(article)
                placed = True
                break
        if not placed:
            clusters.append([article])
    return clusters


@dataclass
class _StoryCandidate:
    """Structural stand-in so clustering stays importable without the scraper."""

    title: str = ""
    url: str = ""
    source: str = ""
    published: Optional[str] = None
    tier: int = 3
    metadata: dict = field(default_factory=dict)
