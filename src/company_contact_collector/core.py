from __future__ import annotations

import csv
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import tldextract
from bs4 import BeautifulSoup

EXTRACT = tldextract.TLDExtract(suffix_list_urls=())
CONTACT_HINT = re.compile(
    r"contact|inquiry|inquiries|support|sales|press|company|about|お問い合わせ|問合せ|"
    r"ご相談|法人|営業|窓口|会社概要",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
ROLE_PREFIXES = {
    "info",
    "contact",
    "inquiry",
    "sales",
    "support",
    "press",
    "pr",
    "ir",
    "recruit",
    "hr",
    "soumu",
    "eigyo",
    "office",
    "help",
    "customer",
    "business",
    "corporate",
}
FREE_MAIL = {"gmail.com", "yahoo.co.jp", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}
OUTPUT_FIELDS = [
    "corporate_number",
    "company_name",
    "revenue_yen",
    "fiscal_year",
    "official_url",
    "contact_type",
    "contact_value",
    "source_url",
    "source_title",
    "confidence",
    "collected_at",
    "crawl_status",
    "notes",
]


@dataclass(frozen=True)
class Company:
    corporate_number: str
    company_name: str
    revenue_yen: int
    fiscal_year: str
    official_url: str


@dataclass(frozen=True)
class Contact:
    corporate_number: str
    company_name: str
    revenue_yen: int
    fiscal_year: str
    official_url: str
    contact_type: str
    contact_value: str
    source_url: str
    source_title: str
    confidence: str
    collected_at: str
    crawl_status: str
    notes: str = ""


def registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip(".")
    ext = EXTRACT(host)
    return ".".join(part for part in (ext.domain, ext.suffix) if part)


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    clean, _ = urldefrag(value)
    return clean.rstrip("/") or clean


def read_companies(path: Path, min_revenue_yen: int) -> list[Company]:
    companies: list[Company] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                revenue = int(str(row.get("revenue_yen", "0")).replace(",", ""))
            except ValueError:
                continue
            official_url = normalize_url(row.get("official_url", ""))
            name = row.get("company_name", "").strip()
            if revenue < min_revenue_yen or not name or not official_url:
                continue
            key = row.get("corporate_number", "").strip() or registrable_domain(official_url) or name
            if key in seen:
                continue
            seen.add(key)
            companies.append(
                Company(
                    corporate_number=row.get("corporate_number", "").strip(),
                    company_name=name,
                    revenue_yen=revenue,
                    fiscal_year=row.get("fiscal_year", "").strip(),
                    official_url=official_url,
                )
            )
    return sorted(companies, key=lambda item: (-item.revenue_yen, item.company_name))


def is_role_email(email: str, official_url: str) -> bool:
    email = email.strip().lower().strip(".,;:()[]{}<>")
    if not EMAIL_RE.fullmatch(email):
        return False
    local, domain = email.rsplit("@", 1)
    if domain in FREE_MAIL or domain.endswith(".example") or "example" in domain:
        return False
    official_domain = registrable_domain(official_url)
    if not official_domain or registrable_domain("https://" + domain) != official_domain:
        return False
    normalized_local = re.split(r"[+._-]", local)[0]
    return normalized_local in ROLE_PREFIXES


def _same_domain(url: str, official_url: str) -> bool:
    return bool(registrable_domain(url)) and registrable_domain(url) == registrable_domain(official_url)


def extract_contacts(html: str, page_url: str, company: Company) -> tuple[list[Contact], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    now = datetime.now(UTC).isoformat()
    found: dict[tuple[str, str], Contact] = {}
    links: list[str] = []

    candidates = set(EMAIL_RE.findall(soup.get_text(" ", strip=True)))
    for anchor in soup.select('a[href^="mailto:"]'):
        candidates.add(anchor.get("href", "")[7:].split("?", 1)[0])
    for email in candidates:
        email = email.lower().strip()
        if is_role_email(email, company.official_url):
            key = ("email", email)
            found[key] = Contact(
                company.corporate_number,
                company.company_name,
                company.revenue_yen,
                company.fiscal_year,
                company.official_url,
                "email",
                email,
                page_url,
                title,
                "high",
                now,
                "ok",
                "public role-based address on official domain",
            )

    for form in soup.find_all("form"):
        method = str(form.get("method", "get")).lower()
        action = normalize_url(urljoin(page_url, str(form.get("action", page_url))))
        context = " ".join(
            [
                title,
                str(form.get("id", "")),
                " ".join(form.get("class", [])),
                form.get_text(" ", strip=True)[:500],
                action,
            ]
        )
        if action and _same_domain(action, company.official_url) and CONTACT_HINT.search(context):
            key = ("inquiry_form", action)
            found[key] = Contact(
                company.corporate_number,
                company.company_name,
                company.revenue_yen,
                company.fiscal_year,
                company.official_url,
                "inquiry_form",
                action,
                page_url,
                title,
                "high" if method == "post" else "medium",
                now,
                "ok",
                f"form detected; method={method}; not submitted",
            )

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = normalize_url(urljoin(page_url, href))
        text = anchor.get_text(" ", strip=True)
        if absolute and _same_domain(absolute, company.official_url) and CONTACT_HINT.search(text + " " + absolute):
            links.append(absolute)
            if re.search(r"contact|inquiry|お問い合わせ|問合せ", text + " " + absolute, re.I):
                key = ("contact_page", absolute)
                found.setdefault(
                    key,
                    Contact(
                        company.corporate_number,
                        company.company_name,
                        company.revenue_yen,
                        company.fiscal_year,
                        company.official_url,
                        "contact_page",
                        absolute,
                        page_url,
                        title,
                        "medium",
                        now,
                        "ok",
                        "contact-like official link; review destination before outreach",
                    ),
                )
    return list(found.values()), list(dict.fromkeys(links))


class Crawler:
    def __init__(self, delay_seconds: float = 1.5, timeout_seconds: float = 15, page_limit: int = 10):
        self.delay_seconds = max(delay_seconds, 1.5)
        self.page_limit = min(max(page_limit, 1), 20)
        self.client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "jp-company-contact-collector/0.2 (+https://github.com/univcorp2-ctrl/jp-company-contact-collector)"},
        )

    def _robots(self, root: str) -> RobotFileParser:
        parsed = urlparse(root)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = RobotFileParser(robots_url)
        try:
            response = self.client.get(robots_url)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                parser.parse([])
        except httpx.HTTPError:
            parser.parse([])
        return parser

    def crawl(self, company: Company) -> list[Contact]:
        queue = [company.official_url]
        visited: set[str] = set()
        contacts: dict[tuple[str, str], Contact] = {}
        robots = self._robots(company.official_url)
        user_agent = self.client.headers["User-Agent"]
        while queue and len(visited) < self.page_limit:
            url = queue.pop(0)
            if url in visited or not _same_domain(url, company.official_url):
                continue
            visited.add(url)
            if not robots.can_fetch(user_agent, url):
                continue
            if len(visited) > 1:
                time.sleep(self.delay_seconds)
            try:
                response = self.client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code in {401, 403, 429}:
                break
            if response.status_code >= 400 or "text/html" not in response.headers.get("content-type", ""):
                continue
            extracted, links = extract_contacts(response.text, str(response.url), company)
            for contact in extracted:
                contacts[(contact.contact_type, contact.contact_value)] = contact
            for link in links:
                if link not in visited and link not in queue:
                    queue.append(link)
        if contacts:
            return sorted(contacts.values(), key=lambda item: (item.contact_type, item.contact_value))
        return [
            Contact(
                company.corporate_number,
                company.company_name,
                company.revenue_yen,
                company.fiscal_year,
                company.official_url,
                "none",
                "",
                company.official_url,
                "",
                "none",
                datetime.now(UTC).isoformat(),
                "no_public_contact_found",
                "manual review may be required",
            )
        ]

    def close(self) -> None:
        self.client.close()


def write_contacts(path: Path, contacts: Iterable[Contact]) -> None:
    rows = sorted(contacts, key=lambda item: (-item.revenue_yen, item.company_name, item.contact_type, item.contact_value))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
