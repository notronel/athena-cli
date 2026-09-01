from typer.testing import CliRunner

from athenanet_cli.main import app

runner = CliRunner()


def test_help_lists_read_only_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "patients" in result.stdout
    assert "appointments" in result.stdout
    assert "documents" in result.stdout


def test_appointment_dates_are_validated_before_api_call() -> None:
    result = runner.invoke(
        app,
        ["appointments", "list", "--patient-id", "1", "--from-date", "2026-09-10", "--to-date", "2026-09-01"],
    )
    assert result.exit_code != 0
    assert "must not be after" in result.stderr


def test_patient_command_requires_configuration() -> None:
    result = runner.invoke(app, ["patients", "search", "--first-name", "Ada"], env={})
    assert result.exit_code != 0
    assert "ATHENA_" in result.stderr
