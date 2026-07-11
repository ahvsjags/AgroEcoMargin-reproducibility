#!/usr/bin/env python3
"""Verify DOI metadata through Crossref and emit MDPI-style reference text."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "AgroEcoMargin_manuscript_v7_5_prose_revision_20260711.md"
OUT = ROOT / "submission_revision"
HEADERS = {"User-Agent": "AgroEcoMargin-reference-verification/1.0 (manuscript preparation)"}
JOURNAL_ABBREVIATIONS = {
    "Nature Food": "Nat. Food", "Nature Communications": "Nat. Commun.",
    "Scientific Data": "Sci. Data", "Remote Sensing of Environment": "Remote Sens. Environ.",
    "IEEE Geoscience and Remote Sensing Magazine": "IEEE Geosci. Remote Sens. Mag.",
    "Environmental Research Letters": "Environ. Res. Lett.",
    "Proceedings of the National Academy of Sciences": "Proc. Natl. Acad. Sci. USA",
    "Proceedings of the National Academy of Sciences of the United States of America": "Proc. Natl. Acad. Sci. USA",
    "Nature Climate Change": "Nat. Clim. Chang.", "Weather and Climate Extremes": "Weather Clim. Extrem.",
    "Plant and Soil": "Plant Soil", "Scientific Reports": "Sci. Rep.",
    "Journal of Human Resources": "J. Hum. Resour.", "Methods in Ecology and Evolution": "Methods Ecol. Evol.",
    "Nature Sustainability": "Nat. Sustain.",
}


def initials(given: str) -> str:
    return "".join(piece[0].upper() + "." for piece in re.findall(r"[A-Za-z]+", given))


def author_text(authors: list[dict]) -> str:
    values = []
    for author in authors:
        family = author.get("family", "").strip()
        given = initials(author.get("given", ""))
        values.append(f"{family}, {given}".strip().rstrip(","))
    return "; ".join(values)


def pages(message: dict) -> str:
    return str(message.get("page") or message.get("article-number") or message.get("locator") or "").replace("--", "-")


def format_crossref(doi: str) -> tuple[str, dict]:
    response = requests.get(f"https://api.crossref.org/works/{doi}", headers=HEADERS, timeout=30)
    response.raise_for_status()
    message = response.json()["message"]
    published = message.get("published-print") or message.get("published-online") or message.get("issued", {})
    year = published.get("date-parts", [[""]])[0][0]
    full_journal = (message.get("container-title") or [""])[0]
    journal = JOURNAL_ABBREVIATIONS.get(full_journal, (message.get("short-container-title") or [full_journal])[0])
    volume = str(message.get("volume", ""))
    issue = str(message.get("issue", ""))
    volume_issue = volume + (f", {issue}" if issue else "")
    formatted = f"{author_text(message.get('author', []))} {message.get('title', [''])[0]}. {journal} {year}, {volume_issue}, {pages(message)}. https://doi.org/{doi}"
    return formatted.replace(" ,", ",").replace(". .", "."), message


def main() -> None:
    source = MANUSCRIPT.read_text(encoding="utf-8")
    raw = source.split("## References\n", 1)[1].strip()
    entries = re.split(r"\n\s*\n(?=\d+\. )", raw)
    doi_entries: list[tuple[int, str, str]] = []
    for index, entry in enumerate(entries):
        number = int(re.match(r"(\d+)\. ", entry).group(1))
        doi_match = re.search(r"https://doi.org/(.+)$", entry.strip())
        if doi_match:
            doi_entries.append((index, entry, doi_match.group(1).strip()))
    checked: dict[int, tuple[str, dict]] = {}
    def fetch(item: tuple[int, str, str]) -> tuple[int, str, dict]:
        index, entry, doi = item
        try:
            formatted, message = format_crossref(doi)
            number = int(re.match(r"(\d+)\. ", entry).group(1))
            return index, f"{number}. {formatted}", {"number": number, "doi": doi, "status": "verified", "crossref_title": message.get("title", [""])[0], "author_count": len(message.get("author", []))}
        except Exception as exc:
            number = int(re.match(r"(\d+)\. ", entry).group(1))
            return index, entry, {"number": number, "doi": doi, "status": "failed", "error": str(exc)}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for index, formatted, record in pool.map(fetch, doi_entries):
            checked[index] = (formatted, record)
    output, audit = [], []
    for index, entry in enumerate(entries):
        if index in checked:
            formatted, record = checked[index]
            output.append(formatted); audit.append(record)
        else:
            number = int(re.match(r"(\d+)\. ", entry).group(1))
            output.append(entry); audit.append({"number": number, "status": "manual_non_doi", "reference": entry})
    OUT.mkdir(exist_ok=True)
    (OUT / "references_v7_6_mdpi_crossref_verified.md").write_text("\n\n".join(output) + "\n", encoding="utf-8")
    (OUT / "references_v7_6_crossref_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {sum(row['status'] == 'verified' for row in audit)} DOI references; {sum(row['status'] == 'failed' for row in audit)} failed.")


if __name__ == "__main__":
    main()
