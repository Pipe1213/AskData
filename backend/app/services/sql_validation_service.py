from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.config import Settings, get_settings
from app.schemas.validation import SQLValidationResult

FORBIDDEN_EXPRESSION_CLASS_NAMES = (
    "Alter",
    "Command",
    "Commit",
    "Create",
    "Delete",
    "Drop",
    "Grant",
    "Insert",
    "Merge",
    "Revoke",
    "Rollback",
    "Transaction",
    "Truncate",
    "Update",
)


class SQLValidationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._forbidden_expression_classes = tuple(
            expression_class
            for class_name in FORBIDDEN_EXPRESSION_CLASS_NAMES
            if (expression_class := getattr(exp, class_name, None)) is not None
        )
        self._aggregate_expression_class = getattr(exp, "AggFunc", None)

    def validate_sql(self, sql: str) -> SQLValidationResult:
        normalized_sql = sql.strip()
        if not normalized_sql:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=True,
                classification="repairable_failure",
                errors=["Generated SQL is empty."],
            )

        try:
            parsed_statements = [
                statement
                for statement in parse(normalized_sql, read="postgres")
                if statement is not None
            ]
        except ParseError as exc:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=True,
                classification="repairable_failure",
                errors=[f"SQL could not be parsed as PostgreSQL: {exc}"],
            )

        if len(parsed_statements) != 1:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=False,
                classification="hard_safety_failure",
                errors=["Only one SQL statement is allowed."],
            )

        expression = parsed_statements[0]

        forbidden_operations = self._find_forbidden_operations(expression)
        if forbidden_operations:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=False,
                classification="hard_safety_failure",
                errors=[
                    "Unsafe SQL operation detected: "
                    + ", ".join(sorted(set(forbidden_operations)))
                ],
            )

        if not self._contains_select(expression):
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=False,
                classification="hard_safety_failure",
                errors=["Only read-only SELECT queries are allowed."],
            )

        warnings: list[str] = []
        validated_expression = expression.copy()

        if self._should_apply_limit(validated_expression):
            validated_expression = validated_expression.limit(
                self.settings.max_result_rows,
                copy=True,
            )
            warnings.append(
                f"Applied LIMIT {self.settings.max_result_rows} to constrain result size."
            )

        return SQLValidationResult(
            original_sql=sql,
            validated_sql=validated_expression.sql(dialect="postgres"),
            is_valid=True,
            can_repair=False,
            classification="valid",
            warnings=warnings,
            detected_tables=self._extract_table_names(validated_expression),
        )

    def _find_forbidden_operations(self, expression: exp.Expression) -> list[str]:
        if not self._forbidden_expression_classes:
            return []

        violations: list[str] = []
        for expression_class in self._forbidden_expression_classes:
            if expression.find(expression_class) is not None:
                violations.append(expression_class.__name__)

        return violations

    def _contains_select(self, expression: exp.Expression) -> bool:
        return expression.find(exp.Select) is not None

    def _should_apply_limit(self, expression: exp.Expression) -> bool:
        if expression.args.get("limit") or expression.args.get("fetch"):
            return False

        if expression.args.get("group") is not None:
            return False

        if self._aggregate_expression_class is not None and expression.find(
            self._aggregate_expression_class
        ):
            return False

        return hasattr(expression, "limit")

    def _extract_table_names(self, expression: exp.Expression) -> list[str]:
        table_names: set[str] = set()
        cte_names = {
            cte.alias
            for cte in expression.find_all(exp.CTE)
            if getattr(cte, "alias", None)
        }

        for table in expression.find_all(exp.Table):
            if table.name in cte_names:
                continue

            schema_name = table.args.get("db")
            if schema_name is not None and getattr(schema_name, "name", None):
                table_names.add(f"{schema_name.name}.{table.name}")
            else:
                table_names.add(table.name)

        return sorted(table_names)
