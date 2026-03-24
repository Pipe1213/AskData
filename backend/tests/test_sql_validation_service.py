from app.services.sql_validation_service import SQLValidationService


def test_validation_rejects_multiple_statements() -> None:
    service = SQLValidationService()

    result = service.validate_sql("SELECT 1; SELECT 2;")

    assert result.is_valid is False
    assert result.classification == "hard_safety_failure"
    assert result.can_repair is False
    assert "Only one SQL statement is allowed." in result.errors


def test_validation_rejects_unsafe_update() -> None:
    service = SQLValidationService()

    result = service.validate_sql("UPDATE payment SET amount = 0")

    assert result.is_valid is False
    assert result.classification == "hard_safety_failure"
    assert result.can_repair is False
    assert any("Unsafe SQL operation detected" in error for error in result.errors)


def test_validation_marks_parse_error_as_repairable() -> None:
    service = SQLValidationService()

    result = service.validate_sql("SELECT * FROM")

    assert result.is_valid is False
    assert result.classification == "repairable_failure"
    assert result.can_repair is True


def test_validation_applies_limit_to_row_level_query() -> None:
    service = SQLValidationService()

    result = service.validate_sql("SELECT customer_id, amount FROM payment")

    assert result.is_valid is True
    assert result.validated_sql is not None
    assert "LIMIT 200" in result.validated_sql.upper()
    assert result.warnings


def test_validation_keeps_aggregate_query_without_limit() -> None:
    service = SQLValidationService()

    result = service.validate_sql(
        "SELECT customer_id, SUM(amount) AS total_amount FROM payment GROUP BY customer_id"
    )

    assert result.is_valid is True
    assert result.validated_sql is not None
    assert "LIMIT 200" not in result.validated_sql.upper()


def test_validation_excludes_cte_aliases_from_detected_tables() -> None:
    service = SQLValidationService()

    result = service.validate_sql(
        """
        WITH customer_counts AS (
            SELECT customer_id, COUNT(*) AS rental_count
            FROM rental
            GROUP BY customer_id
        )
        SELECT customer.customer_id, customer_counts.rental_count
        FROM customer_counts
        JOIN customer ON customer.customer_id = customer_counts.customer_id
        """
    )

    assert result.is_valid is True
    assert result.detected_tables == ["customer", "rental"]
