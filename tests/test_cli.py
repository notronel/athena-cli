from typer.testing import CliRunner

from athenanet_cli.main import app

runner = CliRunner()


def test_help_lists_only_supported_fhir_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "patients" in result.stdout
    assert "documents" in result.stdout
    assert "appointments" not in result.stdout


def test_patient_command_requires_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["patients", "search", "--first-name", "Ada"], env={})
    assert result.exit_code != 0
    assert "ATHENA_" in result.stderr
