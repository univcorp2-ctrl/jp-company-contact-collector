from __future__ import annotations

import argparse
from pathlib import Path

from .core import Crawler, read_companies, write_contacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="company-contact-collector",
        description="公式サイトから公開された法人共通窓口を収集します。フォーム送信は行いません。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="CSVの企業一覧を年商で絞り、公式サイトを低速収集")
    collect.add_argument("--input", required=True, type=Path)
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--min-revenue-yen", type=int, default=0)
    collect.add_argument("--delay-seconds", type=float, default=1.5)
    collect.add_argument("--timeout-seconds", type=float, default=15)
    collect.add_argument("--page-limit", type=int, default=10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command != "collect":
        raise SystemExit(2)
    companies = read_companies(args.input, args.min_revenue_yen)
    crawler = Crawler(args.delay_seconds, args.timeout_seconds, args.page_limit)
    contacts = []
    try:
        for index, company in enumerate(companies, start=1):
            print(f"[{index}/{len(companies)}] {company.company_name}")
            contacts.extend(crawler.crawl(company))
    finally:
        crawler.close()
    write_contacts(args.output, contacts)
    print(f"wrote {len(contacts)} rows to {args.output}")


if __name__ == "__main__":
    main()
