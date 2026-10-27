import pytest

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


@pytest.mark.parametrize(
    "sql",
    [
        # server files
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT pg_catalog.pg_read_file('/etc/passwd', 0, 100)",
        "SELECT * FROM pg_ls_dir('.')",
        "SELECT pg_ls_logdir()",
        "SELECT pg_stat_file('postgresql.conf')",
        # large objects
        "SELECT lo_import('/etc/passwd')",
        "SELECT lo_export(1234, '/tmp/out')",
        "SELECT lo_get(1234)",
        # other servers
        "SELECT * FROM dblink('host=10.0.0.1', 'SELECT 1') AS t(a int)",
        "SELECT dblink_connect('host=10.0.0.1')",
        # sleeping and locks
        "SELECT pg_sleep(30)",
        "SELECT pg_sleep_for('5 minutes')",
        'SELECT "pg_sleep"(1)',
        "WITH waiting AS (SELECT pg_sleep(1) AS x) SELECT * FROM waiting",
        "SELECT pg_advisory_lock(1)",
        # other sessions and server settings
        "SELECT pg_terminate_backend(123)",
        "SELECT pg_cancel_backend(123)",
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT pg_reload_conf()",
        "SELECT pg_rotate_logfile()",
    ],
)
def test_validation_rejects_dangerous_functions_anywhere(sql: str) -> None:
    result = SQLValidationService().validate_sql(sql)

    assert result.is_valid is False
    assert result.classification == "hard_safety_failure"
    assert any("Unsafe SQL function detected" in error for error in result.errors)


@pytest.mark.parametrize(
    "sql",
    [
        "COPY customer TO '/tmp/customers.csv'",
        "COPY (SELECT * FROM customer) TO PROGRAM 'id'",
        "COPY customer FROM '/tmp/in.csv'",
    ],
)
def test_validation_rejects_copy(sql: str) -> None:
    result = SQLValidationService().validate_sql(sql)

    assert result.is_valid is False
    assert result.classification == "hard_safety_failure"


def test_validation_rejects_the_app_persistence_schema() -> None:
    result = SQLValidationService().validate_sql("SELECT question FROM askdata_app.chat_turns")

    assert result.is_valid is False
    assert any("internal schema" in error for error in result.errors)


def test_validation_keeps_ordinary_functions() -> None:
    result = SQLValidationService().validate_sql(
        "SELECT upper(name), date_trunc('month', paid_at), count(*) FROM payments GROUP BY 1, 2"
    )

    assert result.is_valid is True
