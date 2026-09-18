from nexusmind.core.storage import extract_links, extract_frontmatter, get_file_hash

def test_extract_links():
    content = "Hello [[TargetNote|Alias]] and [[40-Domain/00-Index/Master-Index]]!"
    links = extract_links(content)
    assert "TargetNote" in links
    assert "40-Domain/00-Index/Master-Index" in links

def test_extract_frontmatter():
    content = "---\ntitle: Test\ntags: [#test]\n---\n# Header"
    data = extract_frontmatter(content)
    assert data.get("title") == "Test"
    assert data.get("tags") == ["#test"]

def test_get_file_hash():
    h1 = get_file_hash("hello world")
    h2 = get_file_hash("hello world")
    h3 = get_file_hash("hello world 2")
    assert len(h1) == 12
    assert h1 == h2
    assert h1 != h3
