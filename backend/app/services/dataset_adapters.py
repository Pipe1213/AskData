from dataclasses import dataclass, field

from app.db.metadata_models import DatabaseSchema


REVENUE_TOKENS = {"revenue", "sale", "sales", "spend", "spent", "earning", "earnings"}
CATEGORY_TOKENS = {"category", "genre"}
CUSTOMER_TOKENS = {"customer", "customers"}
STAFF_TOKENS = {"staff", "employee", "employees"}
RENTAL_TOKENS = {"rental", "rentals", "rented", "rent"}
TIME_TOKENS = {"date", "dates", "trend", "monthly", "month", "daily", "yearly", "time", "year", "day"}


@dataclass(frozen=True)
class RetrievalColumnBoost:
    table_family: str
    column_names: list[str]
    amount: float


@dataclass(frozen=True)
class RetrievalBoostSet:
    table_boosts: list[tuple[list[str], float]] = field(default_factory=list)
    column_boosts: list[RetrievalColumnBoost] = field(default_factory=list)


class DatasetAdapter:
    name = "generic_postgres"

    def prompt_hints(self, question_tokens: set[str]) -> list[str]:
        return []

    def retrieval_boosts(self, question_tokens: set[str]) -> RetrievalBoostSet:
        return RetrievalBoostSet()


class GenericPostgresAdapter(DatasetAdapter):
    name = "generic_postgres"


class PagilaAdapter(DatasetAdapter):
    name = "pagila"

    def prompt_hints(self, question_tokens: set[str]) -> list[str]:
        hints: list[str] = []
        if question_tokens & REVENUE_TOKENS:
            hints.append("- In this dataset, spend or revenue is often represented by payment.amount.")
        if question_tokens & CATEGORY_TOKENS and question_tokens & REVENUE_TOKENS:
            hints.append(
                "- Category revenue often requires the join path payment -> rental -> inventory -> film_category -> category."
            )
        if question_tokens & STAFF_TOKENS and question_tokens & REVENUE_TOKENS:
            hints.append("- Staff revenue often uses payment.staff_id together with payment.amount.")
        if question_tokens & RENTAL_TOKENS and question_tokens & TIME_TOKENS:
            hints.append("- Rental trends often rely on rental.rental_date.")
        if question_tokens & REVENUE_TOKENS and question_tokens & TIME_TOKENS:
            hints.append("- Revenue trends often rely on payment.payment_date.")
        return hints

    def retrieval_boosts(self, question_tokens: set[str]) -> RetrievalBoostSet:
        boosts = RetrievalBoostSet()

        if question_tokens & REVENUE_TOKENS and question_tokens & CATEGORY_TOKENS:
            boosts.table_boosts.append(
                (["payment", "rental", "inventory", "film_category", "category"], 5.5)
            )
            boosts.column_boosts.append(
                RetrievalColumnBoost(table_family="payment", column_names=["amount"], amount=4.5)
            )

        if question_tokens & REVENUE_TOKENS and question_tokens & CUSTOMER_TOKENS:
            boosts.table_boosts.append((["payment", "customer"], 6.5))
            boosts.column_boosts.append(
                RetrievalColumnBoost(
                    table_family="payment",
                    column_names=["amount", "customer_id"],
                    amount=3.8,
                )
            )

        if question_tokens & REVENUE_TOKENS and question_tokens & STAFF_TOKENS:
            boosts.table_boosts.append((["payment", "staff"], 6.2))
            boosts.column_boosts.append(
                RetrievalColumnBoost(
                    table_family="payment",
                    column_names=["amount", "staff_id"],
                    amount=4.0,
                )
            )

        if question_tokens & RENTAL_TOKENS and question_tokens & TIME_TOKENS:
            boosts.table_boosts.append((["rental"], 3.5))
            boosts.column_boosts.append(
                RetrievalColumnBoost(
                    table_family="rental",
                    column_names=["rental_date"],
                    amount=4.0,
                )
            )

        return boosts


def resolve_dataset_adapter(schema: DatabaseSchema) -> DatasetAdapter:
    table_families = {_canonical_table_family(table.table_name) for table in schema.tables}
    pagila_signature = {"payment", "rental", "inventory", "film_category", "category", "customer"}

    if pagila_signature.issubset(table_families):
        return PagilaAdapter()

    return GenericPostgresAdapter()


def _canonical_table_family(table_name: str) -> str:
    normalized_name = table_name.lower()
    if normalized_name.startswith("payment_p"):
        return "payment"
    if normalized_name.endswith("_list"):
        return normalized_name[: -len("_list")]
    return normalized_name
