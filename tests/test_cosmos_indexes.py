"""Tests to ensure all fields used in .sort() across app/ have simple indexes in Cosmos DB."""
import ast
from pathlib import Path
import mongomock

from app.db.cosmos import (
    init_indexes,
    COURSE_SETTINGS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    FEEDBACK_COLLECTION,
    ISSUES_COLLECTION,
    DIRECT_REVIEWS_COLLECTION,
    REPORT_CHECKLIST_COLLECTION,
)

COLLECTION_MAP = {
    "COURSE_SETTINGS_COLLECTION": COURSE_SETTINGS_COLLECTION,
    "GITHUB_EVENTS_COLLECTION": GITHUB_EVENTS_COLLECTION,
    "FEEDBACK_COLLECTION": FEEDBACK_COLLECTION,
    "ISSUES_COLLECTION": ISSUES_COLLECTION,
    "DIRECT_REVIEWS_COLLECTION": DIRECT_REVIEWS_COLLECTION,
    "REPORT_CHECKLIST_COLLECTION": REPORT_CHECKLIST_COLLECTION,
    "course_settings": COURSE_SETTINGS_COLLECTION,
    "github_events": GITHUB_EVENTS_COLLECTION,
    "feedback": FEEDBACK_COLLECTION,
    "issues": ISSUES_COLLECTION,
    "direct_reviews": DIRECT_REVIEWS_COLLECTION,
    "report_checklist": REPORT_CHECKLIST_COLLECTION,
}


def find_mongo_sort_calls():
    """Scan all python files in app/ to find MongoDB collection .sort() calls using AST."""
    app_dir = Path("app")
    sort_usages = []

    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "sort" and node.args:
                    first_arg = node.args[0]
                    # Only match string arguments like .sort("createdAt", -1)
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        sort_field = first_arg.value

                        # Traverse up the call chain to find the Subscript db[COLLECTION]
                        curr = node.func.value
                        while hasattr(curr, "func") and hasattr(curr.func, "value"):
                            curr = curr.func.value

                        found_coll = None
                        if isinstance(curr, ast.Subscript):
                            if isinstance(curr.slice, ast.Name):
                                found_coll = COLLECTION_MAP.get(curr.slice.id)
                            elif isinstance(curr.slice, ast.Constant):
                                found_coll = COLLECTION_MAP.get(str(curr.slice.value))

                        sort_usages.append({
                            "file": str(py_file),
                            "line": node.lineno,
                            "field": sort_field,
                            "collection": found_coll,
                        })

    return sort_usages


def test_all_sort_fields_have_simple_indexes():
    """Verify that every field used in .sort() has a corresponding simple index in init_indexes."""
    client = mongomock.MongoClient()
    db = client["revisatec"]
    init_indexes(db)

    sort_usages = find_mongo_sort_calls()
    assert len(sort_usages) > 0, "Expected to find at least one .sort() usage in app/"

    for usage in sort_usages:
        coll_name = usage["collection"]
        sort_field = usage["field"]

        assert coll_name is not None, f"Could not determine collection for sort({sort_field}) in {usage['file']}"
        indexes = db[coll_name].index_information()

        # Find simple single-key index on sort_field
        simple_index_fields = [
            info["key"][0][0]
            for info in indexes.values()
            if len(info.get("key", [])) == 1
        ]

        assert sort_field in simple_index_fields, (
            f"Field '{sort_field}' used in .sort() in {usage['file']}:{usage['line']} "
            f"does not have a simple index in collection '{coll_name}'. "
            f"Existing simple indexes: {simple_index_fields}"
        )


def test_report_checklist_has_date_simple_index():
    """Cosmos Mongo 3.6 requirement: report_checklist must have simple index on date."""
    client = mongomock.MongoClient()
    db = client["revisatec"]
    init_indexes(db)

    indexes = db[REPORT_CHECKLIST_COLLECTION].index_information()
    simple_keys = [info["key"][0][0] for info in indexes.values() if len(info.get("key", [])) == 1]

    assert "groupId" in simple_keys
    assert "date" in simple_keys


def test_report_service_does_not_call_mongo_sort():
    """Verify that app/services/report.py does not call .sort() on MongoDB cursor."""
    report_file = Path("app/services/report.py").read_text(encoding="utf-8")
    assert ".sort(" not in report_file, (
        "app/services/report.py should not use .sort() on Mongo cursor; "
        "it should sort in Python (e.g. sorted(...) or .sort())."
    )
