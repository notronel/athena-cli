from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .client import AthenaClient, AthenaError
from .config import AthenaSettings

app = typer.Typer(help="Read-only athenahealth sandbox CLI.", no_args_is_help=True)
auth_app = typer.Typer(help="Credential and connection checks.")
patients_app = typer.Typer(help="Read-only patient lookup.")
appointments_app = typer.Typer(help="Read-only appointment lookup.")
documents_app = typer.Typer(help="Read-only document metadata lookup.")
app.add_typer(auth_app, name="auth")
app.add_typer(patients_app, name="patients")
app.add_typer(appointments_app, name="appointments")
app.add_typer(documents_app, name="documents")
console = Console()


def _client() -> AthenaClient:
    try:
        return AthenaClient(AthenaSettings())
    except ValidationError as exc:
        missing = ", ".join(error["loc"][0].upper() for error in exc.errors())
        raise typer.BadParameter(f"Missing or invalid ATHENA_ environment configuration: {missing}") from exc


def _date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise typer.BadParameter("Use YYYY-MM-DD.") from exc


def _display(rows: Sequence[dict[str, Any]] | dict[str, Any], as_json: bool, fields: list[str]) -> None:
    records = [rows] if isinstance(rows, dict) else list(rows)
    if as_json:
        console.print_json(json.dumps(records, default=str))
        return
    if not records:
        console.print("No matching records.")
        return
    table = Table(show_header=True, header_style="bold")
    for field in fields:
        table.add_column(field.replace("_", " ").title())
    for record in records:
        table.add_row(*(str(record.get(field, "")) for field in fields))
    console.print(table)


def _run(action: Any) -> None:
    try:
        action()
    except AthenaError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1) from exc


@auth_app.command("check")
def auth_check() -> None:
    """Validate environment credentials without retrieving patient data."""
    def action() -> None:
        with _client() as client:
            client.authenticate()
        console.print("Authentication succeeded.")
    _run(action)


@patients_app.command("search")
def patients_search(
    patient_id: Annotated[str | None, typer.Option()] = None,
    first_name: Annotated[str | None, typer.Option()] = None,
    last_name: Annotated[str | None, typer.Option()] = None,
    dob: Annotated[str | None, typer.Option(callback=_date)] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search patients using one or more permitted identifiers."""
    _run(lambda: _display(_client_call("search_patients", patient_id=patient_id, first_name=first_name, last_name=last_name, dob=dob, limit=limit), as_json, ["patientid", "firstname", "lastname", "dob"]))


@appointments_app.command("list")
def appointments_list(
    patient_id: Annotated[str, typer.Option()],
    from_date: Annotated[str, typer.Option(callback=_date)],
    to_date: Annotated[str, typer.Option(callback=_date)],
    department_id: Annotated[str | None, typer.Option()] = None,
    status: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List a patient's appointments within an inclusive date range."""
    if from_date > to_date:
        raise typer.BadParameter("--from-date must not be after --to-date.")
    _run(lambda: _display(_client_call("list_appointments", patient_id=patient_id, from_date=from_date, to_date=to_date, department_id=department_id, status=status, limit=limit), as_json, ["appointmentid", "date", "time", "status", "departmentid"]))


@documents_app.command("list")
def documents_list(
    patient_id: Annotated[str, typer.Option()],
    from_date: Annotated[str | None, typer.Option(callback=_date)] = None,
    to_date: Annotated[str | None, typer.Option(callback=_date)] = None,
    document_type: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List document metadata for a patient; document content is never downloaded."""
    if from_date and to_date and from_date > to_date:
        raise typer.BadParameter("--from-date must not be after --to-date.")
    _run(lambda: _display(_client_call("list_documents", patient_id=patient_id, from_date=from_date, to_date=to_date, document_type=document_type, limit=limit), as_json, ["documentid", "documenttype", "createddate", "departmentid"]))


@documents_app.command("get")
def documents_get(
    patient_id: Annotated[str, typer.Option()],
    document_id: Annotated[str, typer.Option()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Retrieve one document's permitted metadata; document content is never downloaded."""
    _run(lambda: _display(_client_call("get_document", patient_id=patient_id, document_id=document_id), as_json, ["documentid", "documenttype", "createddate", "departmentid", "status"]))


def _client_call(method: str, **kwargs: Any) -> Any:
    with _client() as client:
        return getattr(client, method)(**kwargs)
