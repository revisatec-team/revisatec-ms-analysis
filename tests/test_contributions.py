"""Tests for GET /groups/{id}/contributions."""
from fastapi.testclient import TestClient

from app.db.cosmos import COURSE_SETTINGS_COLLECTION, FEEDBACK_COLLECTION, GITHUB_EVENTS_COLLECTION


def _configure_group(db, group_id=7, course_id=5):
    db[COURSE_SETTINGS_COLLECTION].insert_one({
        "courseId": course_id,
        "rubric": {"criteria": [{"name": "Calidad", "weight": 60.0}, {"name": "Revisiones", "weight": 40.0}]},
    })
    db[FEEDBACK_COLLECTION].insert_one({"groupId": group_id, "courseId": course_id, "groupName": "Grupo 7"})


def test_contributions_per_member(client: TestClient, mock_db):
    _configure_group(mock_db)
    events = [
        {"id": "c1", "groupId": 7, "type": "commit", "author": "ana", "reviewers": [], "createdAt": 1},
        {"id": "c2", "groupId": 7, "type": "commit", "author": "ana", "reviewers": [], "createdAt": 2},
        {"id": "c3", "groupId": 7, "type": "commit", "author": "ana", "reviewers": [], "createdAt": 3},
        {"id": "c4", "groupId": 7, "type": "commit", "author": "luis", "reviewers": [], "createdAt": 4},
        {"id": "p1", "groupId": 7, "type": "pr", "author": "luis", "reviewers": ["ana", "eva"], "createdAt": 5},
        {"id": "p2", "groupId": 7, "type": "pr", "author": "ana", "reviewers": ["ana"], "createdAt": 6},
        {"id": "x1", "groupId": 8, "type": "commit", "author": "otro", "reviewers": [], "createdAt": 7},
    ]
    mock_db[GITHUB_EVENTS_COLLECTION].insert_many(events)

    res = client.get("/groups/7/contributions")
    assert res.status_code == 200
    data = res.json()
    assert data["groupId"] == 7
    assert data["totalCommits"] == 4
    assert data["totalPrs"] == 2
    by_user = {m["githubUser"]: m for m in data["items"]}
    assert set(by_user) == {"ana", "luis", "eva"}
    assert by_user["ana"] == {"githubUser": "ana", "commits": 3, "prs": 1, "reviews": 1, "percent": 75}
    assert by_user["luis"]["percent"] == 25 and by_user["luis"]["prs"] == 1
    # quien solo revisa aparece con 0 commits; revisar el propio PR no cuenta
    assert by_user["eva"] == {"githubUser": "eva", "commits": 0, "prs": 0, "reviews": 1, "percent": 0}
    assert data["items"][0]["githubUser"] == "ana"


def test_contributions_group_without_events(client: TestClient, mock_db):
    _configure_group(mock_db)
    res = client.get("/groups/7/contributions")
    assert res.status_code == 200
    assert res.json() == {"groupId": 7, "totalCommits": 0, "totalPrs": 0, "items": []}


def test_contributions_unconfigured_group(client: TestClient):
    res = client.get("/groups/99/contributions")
    assert res.status_code == 404
    assert res.json()["error"] == "El grupo 99 no está configurado en MS2"
