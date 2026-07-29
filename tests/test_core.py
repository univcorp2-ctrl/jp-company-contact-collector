from pathlib import Path

from company_contact_collector.core import Company, extract_contacts, is_role_email, read_companies, write_contacts


def company() -> Company:
    return Company("123", "Acme株式会社", 2_000_000_000, "2025", "https://acme.co.jp")


def test_role_email_policy() -> None:
    assert is_role_email("info@acme.co.jp", "https://acme.co.jp")
    assert is_role_email("sales-team@acme.co.jp", "https://acme.co.jp")
    assert not is_role_email("taro.yamada@acme.co.jp", "https://acme.co.jp")
    assert not is_role_email("info@gmail.com", "https://acme.co.jp")
    assert not is_role_email("info@other.co.jp", "https://acme.co.jp")
    assert not is_role_email("info@example.co.jp", "https://example.co.jp")


def test_extract_email_form_and_same_domain_links() -> None:
    html = """
    <html><head><title>お問い合わせ</title></head><body>
      <a href="mailto:info@acme.co.jp">mail</a>
      <a href="mailto:taro.yamada@acme.co.jp">personal</a>
      <form action="/contact/send" method="post"><label>お問い合わせ</label></form>
      <a href="/company/contact">お問い合わせ</a>
      <a href="https://evil.example/contact">outside</a>
    </body></html>
    """
    contacts, links = extract_contacts(html, "https://acme.co.jp/contact", company())
    values = {(item.contact_type, item.contact_value) for item in contacts}
    assert ("email", "info@acme.co.jp") in values
    assert ("inquiry_form", "https://acme.co.jp/contact/send") in values
    assert ("contact_page", "https://acme.co.jp/company/contact") in values
    assert all("evil.example" not in value for _, value in values)
    assert all("evil.example" not in link for link in links)


def test_revenue_filter_and_dedupe(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "corporate_number,company_name,revenue_yen,fiscal_year,official_url\n"
        "1,A社,2000,2025,https://a.invalid.jp\n"
        "1,A社重複,3000,2025,https://a.invalid.jp\n"
        "2,B社,100,2025,https://b.invalid.jp\n",
        encoding="utf-8",
    )
    rows = read_companies(source, 1000)
    assert len(rows) == 1
    assert rows[0].company_name == "A社"


def test_csv_is_utf8_sig(tmp_path: Path) -> None:
    html = '<html><title>Contact</title><a href="mailto:info@acme.co.jp">mail</a></html>'
    contacts, _ = extract_contacts(html, "https://acme.co.jp/contact", company())
    target = tmp_path / "out.csv"
    write_contacts(target, contacts)
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "contact_type" in target.read_text(encoding="utf-8-sig")
