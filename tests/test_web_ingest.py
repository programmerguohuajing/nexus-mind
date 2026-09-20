from nexusmind.core.web_ingest import _validate_url, extract_web_page


def test_extract_web_page_ignores_navigation_and_scripts():
    html = """
    <html>
      <head><title> Example Article </title><style>.x{}</style></head>
      <body>
        <nav>Navigation should not be captured</nav>
        <main>
          <h1>Example Article</h1>
          <p>This is the useful article body with enough content to be ingested.</p>
          <p>Second paragraph keeps the extracted content meaningful.</p>
        </main>
        <script>alert('ignore me')</script>
      </body>
    </html>
    """
    result = extract_web_page(html, "https://example.com/article")
    assert result["title"] == "Example Article"
    assert "useful article body" in result["content"]
    assert "Navigation should not be captured" not in result["content"]
    assert "ignore me" not in result["content"]


def test_web_ingest_rejects_private_targets_by_default():
    for url in (
        "http://127.0.0.1/admin",
        "http://10.0.0.2/internal",
        "http://192.168.1.10/",
        "http://localhost:8080/",
    ):
        try:
            _validate_url(url)
        except ValueError as exc:
            assert "内网" in str(exc) or "本机" in str(exc)
        else:
            raise AssertionError(f"private URL was accepted: {url}")


def test_web_ingest_allows_private_targets_for_local_agent():
    assert _validate_url("http://127.0.0.1:8080/article", allow_private=True) == "http://127.0.0.1:8080/article"
    assert _validate_url("http://192.168.1.20/wiki", allow_private=True) == "http://192.168.1.20/wiki"
    assert _validate_url("http://localhost:3000/docs", allow_private=True) == "http://localhost:3000/docs"
