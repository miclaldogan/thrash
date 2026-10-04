from conftest import make_repo
from thrash import git_context as gc
from thrash.config import Config
from thrash.privacy import IgnoreRules, redact


def test_default_ignores():
    r = IgnoreRules()
    for p in (".env", "a/.env.local", "x.pem", "keys/server.key", "credentials.json", "secrets.yaml",
              "node_modules/a/b.js", "src/.venv/lib.py", "dist/x.js", ".git/config", "build/out"):
        assert r.is_ignored(p), p
    for p in ("README.md", "src/main.py", "docs/notes.md", "environment.md"):
        assert not r.is_ignored(p), p


def test_thrashignore_file(tmp_path):
    (tmp_path / ".thrashignore").write_text("# c\nprivate/\n*.draft\ndocs/legal.md\n")
    r = IgnoreRules.load(tmp_path)
    assert r.is_ignored("private/a.txt") and r.is_ignored("x/y.draft") and r.is_ignored("docs/legal.md")
    assert not r.is_ignored("docs/other.md")


def test_redaction():
    text, n = redact('api_key = "sk-abcdefghijklmnopqrstuvwxyz123"\nname = ok\npassword: hunter2hunter2')
    assert "abcdefgh" not in text and "hunter2" not in text and "name = ok" in text and n >= 2
    t2, n2 = redact("-----BEGIN RSA PRIVATE KEY-----\nabc")
    assert "abc" not in t2 and n2 == 1


def test_secrets_never_reach_context(tmp_path):
    repo = make_repo(tmp_path / "r", {"README.md": "# r\n", ".env": "TOKEN=supersecretvalue123\n",
                                      "secrets.txt": "x", "private/plan.md": "launch plan",
                                      "notes.md": "token = abcdefghijklmnop12345\n"})
    (repo / ".thrashignore").write_text("private/\n")
    rules = IgnoreRules.load(repo)
    ctx = gc.gather_context(repo, Config(), rules, 1e9)
    blob = ctx.render()
    assert "supersecretvalue" not in blob and "launch plan" not in blob and "abcdefghijklmnop" not in blob
    assert ".env" not in ctx.allowed_paths and "private/plan.md" not in ctx.allowed_paths
    assert "README.md" in ctx.allowed_paths
