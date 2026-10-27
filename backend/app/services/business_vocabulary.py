"""General business words shared by the planner and retrieval.

Each concept maps words a question may use to words that often appear in table and column
names of business databases. Nothing here names a table or column of a particular dataset:
matching is on the words inside names (`sales_reps` -> {"sale", "rep"}), and dates are found
by column type, not by name.
"""

from dataclasses import dataclass

from app.utils.text import STOPWORDS, significant_tokens, tokenize_text


@dataclass(frozen=True)
class Concept:
    question_words: frozenset[str]
    name_words: frozenset[str]
    is_measure: bool = False


def _concept(question_words: set[str], name_words: set[str], is_measure: bool = False) -> Concept:
    return Concept(frozenset(question_words), frozenset(name_words), is_measure)


# Question words are in the normalised form `significant_tokens` produces ("sales" -> "sale").
CONCEPTS: dict[str, Concept] = {
    "money": _concept(
        {"revenue", "sale", "spend", "spent", "earning", "income", "turnover", "paid"},
        {"amount", "payment", "sale", "revenue", "price", "total", "paid", "spent", "income", "invoice"},
        is_measure=True,
    ),
    "customer": _concept({"customer", "buyer", "client", "shopper"}, {"customer", "buyer", "client"}),
    "staff": _concept(
        {"staff", "employee", "rep", "representative", "seller", "salesperson", "agent"},
        {"staff", "employee", "rep", "seller", "agent"},
    ),
    "category": _concept({"category", "genre"}, {"category", "genre"}),
    "product": _concept({"product", "item", "sku"}, {"product", "item", "sku"}),
    "brand": _concept({"brand"}, {"brand"}),
    "location": _concept(
        {"region", "market", "country", "city", "location"},
        {"region", "market", "country", "city", "location"},
    ),
    "order": _concept({"order", "ordered", "purchase", "purchased"}, {"order", "purchase"}),
    "return": _concept({"return", "returned", "refund"}, {"return", "refund"}),
    "shipping": _concept(
        {"shipment", "shipped", "shipping", "delivery", "delivered", "carrier"},
        {"shipment", "shipping", "delivery", "carrier"},
    ),
    "rental": _concept({"rental", "rent", "rented"}, {"rental", "rent"}),
}

TIME_WORDS = {
    "date", "trend", "time", "daily", "day", "weekly", "week", "monthly", "month",
    "quarterly", "quarter", "yearly", "year", "annual",
}
COUNT_WORDS = {"count", "number", "many"}
AVERAGE_WORDS = {"average", "avg", "mean"}
AVERAGE_NAME_WORDS = {"avg", "average", "mean"}
COMPARISON_WORDS = {"compare", "comparison", "versus", "vs"}
TOPK_WORDS = {"top", "highest", "most", "best"}
LABEL_NAME_WORDS = {"name", "title"}

TEMPORAL_TYPE_MARKERS = ("date", "timestamp", "time")
NUMERIC_TYPE_MARKERS = ("numeric", "decimal", "money", "real", "double", "integer", "bigint", "smallint")
# Bookkeeping dates (when a row was last edited) rarely answer a business question.
AUDIT_NAME_WORDS = {"update", "updated", "modified"}


def word_forms(token: str) -> set[str]:
    """The token plus its likely base forms, so "spending" and "priced" match "spend" and "price"."""
    forms = {token}
    for suffix, min_length in (("ing", 6), ("ed", 5)):
        if token.endswith(suffix) and len(token) >= min_length:
            stem = token[: -len(suffix)]
            forms |= {stem, stem + "e"}
            if len(stem) > 2 and stem[-1] == stem[-2]:
                forms.add(stem[:-1])
    return forms


def _mentions(question_tokens: set[str], words: frozenset[str]) -> bool:
    return any(word_forms(token) & words for token in question_tokens)


def concepts_in(question_tokens: set[str]) -> list[Concept]:
    return [concept for concept in CONCEPTS.values() if _mentions(question_tokens, concept.question_words)]


def has_money_intent(question_tokens: set[str]) -> bool:
    return _mentions(question_tokens, CONCEPTS["money"].question_words)


def has_time_intent(question_tokens: set[str]) -> bool:
    return bool(question_tokens & TIME_WORDS)


def expand_question_tokens(question_tokens: set[str]) -> set[str]:
    """Question words plus the name words of every concept the question mentions."""
    expanded = set(question_tokens)
    for concept in concepts_in(question_tokens):
        expanded |= concept.name_words
    return expanded


def name_words(name: str) -> set[str]:
    return significant_tokens(name.replace("_", " "))


def head_word(name: str) -> str:
    """The last word of a name, the thing it is about: `sales_reps` -> "rep", `order_items` -> "item"."""
    words = [word for word in tokenize_text(name.replace("_", " ")) if word not in STOPWORDS and word != "list"]
    return words[-1] if words else name.lower()


def is_temporal_type(data_type: str) -> bool:
    normalized = data_type.lower()
    return any(marker in normalized for marker in TEMPORAL_TYPE_MARKERS) and "interval" not in normalized


def is_numeric_type(data_type: str) -> bool:
    normalized = data_type.lower()
    return any(marker in normalized for marker in NUMERIC_TYPE_MARKERS)


def is_business_date_column(column_name: str, data_type: str) -> bool:
    return is_temporal_type(data_type) and not name_words(column_name) & AUDIT_NAME_WORDS


def is_label_column(column_name: str, data_type: str) -> bool:
    lowered = data_type.lower()
    is_text = "char" in lowered or "text" in lowered
    return is_text and bool(name_words(column_name) & LABEL_NAME_WORDS)


def is_key_column(column_name: str) -> bool:
    lowered = column_name.lower()
    return lowered == "id" or lowered.endswith("_id")
