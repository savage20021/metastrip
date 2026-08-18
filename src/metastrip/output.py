"""Rendering: rich console output by default, JSON on request."""
from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import MetadataReport

console = Console()


def render_json(payloads: list) -> None:
    payloads = [p.to_dict() if hasattr(p, "to_dict") else p for p in payloads]
    print(json.dumps(payloads[0] if len(payloads) == 1 else payloads, indent=2))


def render_report(report: MetadataReport) -> None:
    header = f"[bold]{report.path}[/bold]  [dim]({report.filetype})[/dim]"
    console.print(header)

    if report.error:
        console.print(f"  [red]Error reading metadata: {report.error}[/red]")
        return

    _render_privacy(report)

    for name, section in report.sections.items():
        table = Table(title=name, title_justify="left", show_header=False,
                      pad_edge=False, box=None, padding=(0, 2))
        table.add_column(style="cyan", no_wrap=True, min_width=24)
        table.add_column(style="white", overflow="fold")
        for key, value in section.items():
            table.add_row(key, value)
        console.print(Panel(table, border_style="dim"))

    for note in report.notes:
        console.print(f"  [dim]{note}[/dim]")


def render_strip(result) -> None:
    if result.error:
        console.print(f"  [red]Strip failed: {result.error}[/red]")
        return
    console.print(f"[green]✔ Clean copy written:[/green] [bold]{result.output}[/bold]")
    if result.removed:
        console.print("  Removed: " + ", ".join(f"[cyan]{s}[/cyan]" for s in result.removed))
    for note in result.notes:
        style = "yellow" if note.startswith("warning") else "dim"
        console.print(f"  [{style}]{note}[/{style}]")


def render_batch(reports: list[MetadataReport], strips: dict, skipped: int) -> None:
    table = Table(title=f"Scanned {len(reports)} file(s)", title_justify="left")
    table.add_column("File", overflow="fold")
    table.add_column("Type", style="dim")
    table.add_column("GPS")
    table.add_column("Device")
    table.add_column("Software")
    table.add_column("Author")
    table.add_column("Times", justify="right")
    if strips:
        table.add_column("Cleaned")

    gps_count = ident_count = error_count = 0
    for r in reports:
        p = r.privacy
        if r.error:
            error_count += 1
            row = [str(r.path.name), r.filetype, "[red]error[/red]", r.error, "", "", ""]
        else:
            if p.gps:
                gps_count += 1
                gps_cell = f"[red]{p.gps['latitude']}, {p.gps['longitude']}[/red]"
            else:
                gps_cell = "[dim]—[/dim]"
            if p.any_present():
                ident_count += 1
            device = " ".join(v for v in (p.device_make, p.device_model) if v) or "[dim]—[/dim]"
            row = [str(r.path.name), r.filetype, gps_cell, device,
                   p.software or "[dim]—[/dim]", p.author or "[dim]—[/dim]",
                   str(len(p.timestamps)) if p.timestamps else "[dim]0[/dim]"]
        if strips:
            s = strips.get(r.path)
            if s is None:
                row.append("[dim]—[/dim]")
            elif s.error:
                row.append("[red]failed[/red]")
            else:
                row.append("[green]✔[/green]")
        table.add_row(*row)

    console.print(table)
    summary = (f"[red]{gps_count} with GPS[/red] · "
               f"[yellow]{ident_count} with identifying data[/yellow] · "
               f"{len(reports) - ident_count} clean")
    if error_count:
        summary += f" · [red]{error_count} error(s)[/red]"
    if skipped:
        summary += f" · [dim]{skipped} unsupported file(s) skipped[/dim]"
    console.print(summary)
    for r in reports:
        s = strips.get(r.path) if strips else None
        if s and s.error:
            console.print(f"  [red]{r.path.name}: {s.error}[/red]")


def _render_privacy(report: MetadataReport) -> None:
    p = report.privacy
    if not p.any_present():
        console.print("  [green]No privacy-sensitive fields detected.[/green]")
        return

    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 2))
    table.add_column(style="bold", no_wrap=True, min_width=24)
    table.add_column(overflow="fold")

    if p.gps:
        coords = f"{p.gps['latitude']}, {p.gps['longitude']}"
        if "altitude_m" in p.gps:
            coords += f"  (alt {p.gps['altitude_m']} m)"
        table.add_row("[red]GPS location[/red]", f"[red]{coords}[/red]")
        table.add_row("[red]Map link[/red]", f"[red][link={p.gps['maps_url']}]{p.gps['maps_url']}[/link][/red]")
    if p.device_make or p.device_model:
        device = " ".join(v for v in (p.device_make, p.device_model) if v)
        table.add_row("[yellow]Device[/yellow]", device)
    if p.software:
        table.add_row("[yellow]Software[/yellow]", p.software)
    if p.author:
        table.add_row("[yellow]Author[/yellow]", p.author)
    for label, value in p.serial_numbers.items():
        table.add_row(f"[yellow]{label}[/yellow]", value)
    for label, value in p.timestamps.items():
        table.add_row(f"[yellow]{label}[/yellow]", value)

    console.print(Panel(table, title="[bold]Privacy-sensitive metadata[/bold]",
                        title_align="left", border_style="red" if p.gps else "yellow"))
