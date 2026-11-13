"""Tests for scripts.seed_demo: fetching MS1 members, deterministic build_events, and dry-run execution."""
import pytest
from scripts.seed_demo import (
    GROUPS,
    COURSES,
    build_events,
    fetch_ms1_members,
    run,
)


def test_fetch_ms1_members_formats_and_filtering(monkeypatch):
    """fetch_ms1_members correctly parses membersRes.members, items, lists, and filters empty users."""
    import httpx

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    # Format 1: {"members": [...]} (used by front in src/pages/GroupDetail.jsx)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, headers, timeout: FakeResponse({
            "members": [
                {"githubUser": "estudiante1"},
                {"githubUser": "estudiante2"},
                {"githubUser": ""},
                {"githubUser": None},
                {"githubUser": "estudiante1"},  # duplicate
            ]
        }),
    )
    users = fetch_ms1_members(1, "dummy-key")
    assert users == ["estudiante1", "estudiante2"]

    # Format 2: raw list of dicts
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, headers, timeout: FakeResponse([
            {"githubUser": "user_a"},
            {"githubUser": "user_b"},
        ]),
    )
    users2 = fetch_ms1_members(2, "dummy-key")
    assert users2 == ["user_a", "user_b"]

    # Format 3: {"items": [...]}
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, headers, timeout: FakeResponse({
            "items": [{"githubUser": "user_x"}]
        }),
    )
    users3 = fetch_ms1_members(3, "dummy-key")
    assert users3 == ["user_x"]


def test_build_events_works_with_two_authors_and_distinct_reviewers():
    """build_events works with 2 authors and ensures all PR reviewers are distinct from author."""
    g = dict(
        name="Grupo Test",
        course=1,
        commits=10,
        weeks=[0, 1, 2, 3],
        prs=4,
        reviewed=4,
        wip=1,
        topics=["modulo a", "modulo b", "modulo c"],
        authors=["dev1", "dev2"],
    )
    now_ms = 1700000000000

    events = build_events(gid=1, g=g, min_reviewers=1, now_ms=now_ms)
    assert len(events) == g["commits"] + g["prs"]

    commits = [e for e in events if e["type"] == "commit"]
    prs = [e for e in events if e["type"] == "pr"]

    assert len(commits) == 10
    assert len(prs) == 4

    for c in commits:
        assert c["author"] in ("dev1", "dev2")
        assert c["reviewers"] == []

    for pr in prs:
        assert pr["author"] in ("dev1", "dev2")
        # Reviewers must be non-empty because reviewed == 4
        assert len(pr["reviewers"]) > 0
        # Reviewer must NOT be the author of the PR
        for reviewer in pr["reviewers"]:
            assert reviewer != pr["author"]
            assert reviewer in ("dev1", "dev2")

    # Determinism check: running with same gid produces identical results
    events2 = build_events(gid=1, g=g, min_reviewers=1, now_ms=now_ms)
    assert events == events2


def test_run_dry_run_with_mocked_httpx(monkeypatch, capsys):
    """run(apply=False) uses githubUser from MS1, prints authors, and does not write to database."""
    import httpx

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/calendar/events" in url:
            return FakeResponse({
                "items": [
                    {"title": "Hito 1", "date": 1700000000000},
                    {"title": "Hito 2", "date": 1705000000000},
                ]
            })
        if "/members" in url:
            # Extract group id from url like ".../groups/4/members"
            gid_str = url.split("/groups/")[1].split("/members")[0]
            return FakeResponse({
                "members": [
                    {"githubUser": f"gh_user_{gid_str}_1"},
                    {"githubUser": f"gh_user_{gid_str}_2"},
                ]
            })
        raise ValueError(f"Unexpected url: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setenv("APIM_KEY", "test-apim-key")

    plan = run(apply=False)

    captured = capsys.readouterr().out
    assert "Modo: DRY-RUN (no escribe)" in captured

    for gid, g in GROUPS.items():
        expected_authors = [f"gh_user_{gid}_1", f"gh_user_{gid}_2"]
        assert g["authors"] == expected_authors
        assert f"grupo {gid}" in captured
        assert f"gh_user_{gid}_1" in captured

        # Verify events generated in plan
        assert gid in plan
        evs = plan[gid]
        assert len(evs) > 0
        for ev in evs:
            assert ev["author"] in expected_authors
            if ev["type"] == "pr":
                for r in ev["reviewers"]:
                    assert r != ev["author"]


def test_run_exits_when_group_has_no_github_users(monkeypatch):
    """run() terminates with sys.exit and mentions group id if group has no members with githubUser."""
    import httpx

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def fake_get(url, headers=None, params=None, timeout=None):
        if "/calendar/events" in url:
            return FakeResponse({
                "items": [{"title": "Hito 1", "date": 1700000000000}]
            })
        if "/members" in url:
            # Group 5 returns empty members
            if "/groups/5/members" in url:
                return FakeResponse({"members": []})
            return FakeResponse({
                "members": [{"githubUser": "valido"}]
            })
        raise ValueError(f"Unexpected url: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setenv("APIM_KEY", "test-apim-key")

    with pytest.raises(SystemExit) as exc_info:
        run(apply=False)

    assert "5" in str(exc_info.value)
    assert "githubUser" in str(exc_info.value)
