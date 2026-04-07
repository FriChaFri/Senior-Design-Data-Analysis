"""Read requirement data from the team's Needs+Specs workbook."""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass(frozen=True)
class RequirementSpec:
    """One row from the authoritative Specs sheet."""

    spec_id: str
    need_id_ref: str
    description: str
    justification: str
    required: bool


def _load_shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []

    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for shared_item in root.findall("main:si", _NS):
        values.append("".join(node.text or "" for node in shared_item.iterfind(".//main:t", _NS)))
    return values


def _sheet_targets(book: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(book.read("xl/workbook.xml"))
    rels_root = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    rel_map = {node.attrib["Id"]: node.attrib["Target"] for node in rels_root}

    targets: dict[str, str] = {}
    for sheet in workbook_root.find("main:sheets", _NS):
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        targets[sheet.attrib["name"]] = f"xl/{rel_map[rel_id]}"
    return targets


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iterfind(".//main:t", _NS))

    value_node = cell.find("main:v", _NS)
    if value_node is None:
        return ""

    if cell_type == "s":
        return shared_strings[int(value_node.text)]
    return value_node.text or ""


def _column_label(cell_ref: str) -> str:
    letters: list[str] = []
    for char in cell_ref:
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters)


def load_requirement_specs(workbook_path: str | Path) -> list[RequirementSpec]:
    """Parse the authoritative Specs sheet from the workbook."""

    path = Path(workbook_path)
    with zipfile.ZipFile(path) as book:
        shared_strings = _load_shared_strings(book)
        target = _sheet_targets(book)["Specs"]
        root = ET.fromstring(book.read(target))

    rows: list[RequirementSpec] = []
    for row in root.iterfind(".//main:row", _NS):
        row_values = {
            _column_label(cell.attrib["r"]): _cell_value(cell, shared_strings)
            for cell in row.findall("main:c", _NS)
        }
        if row_values.get("A") in ("", "Spec ID"):
            continue

        rows.append(
            RequirementSpec(
                spec_id=row_values.get("A", "").strip(),
                need_id_ref=row_values.get("B", "").strip(),
                description=row_values.get("C", "").strip(),
                justification=row_values.get("D", "").strip(),
                required=row_values.get("E", "").strip().upper() == "Y",
            )
        )
    return rows
