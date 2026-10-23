"""Create collections, the Atlas Search index (case text search) and the Atlas Vector Search index
(similar-case retrieval by fingerprint).

    python backend/scripts/setup_atlas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo.errors import OperationFailure  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402

from config import get_settings  # noqa: E402
from services.atlas import COLLECTIONS, FINGERPRINT_DIM, MongoRepository  # noqa: E402

SEARCH_DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "title": {"type": "string"},
            "notes": {"type": "string"},
            "researcher": {"type": "string"},
            "tags": {"type": "string"},
            "hypothesis": {"type": "string"},
            "status": {"type": "token"},
            "report": {"type": "document", "fields": {"summary": {"type": "string"}}},
        },
    }
}

# Atlas Vector Search over the numeric case fingerprint (see services.atlas.fingerprint).
VECTOR_DEFINITION = {
    "fields": [{"type": "vector", "path": "fingerprint", "numDimensions": FINGERPRINT_DIM, "similarity": "cosine"}]
}


def main():
    s = get_settings()
    if not s.mongodb_uri:
        sys.exit("Set MONGODB_URI in .env first.")
    repo = MongoRepository(s.mongodb_uri, s.mongodb_db, s.atlas_search_index)
    existing = set(repo.db.list_collection_names())
    for c in COLLECTIONS:
        if c not in existing:
            repo.db.create_collection(c)
    print(f"collections ready in '{s.mongodb_db}': {', '.join(COLLECTIONS)}")
    ensure_index(repo, s.atlas_search_index, SEARCH_DEFINITION, "search")
    ensure_index(repo, s.atlas_vector_index, VECTOR_DEFINITION, "vectorSearch")


def ensure_index(repo, name, definition, kind):
    try:
        names = {i["name"] for i in repo.db.cases.list_search_indexes()}
        if name in names:
            repo.db.cases.update_search_index(name, definition)
            print(f"updated {kind} index '{name}'")
        else:
            repo.db.cases.create_search_index(SearchIndexModel(definition=definition, name=name, type=kind))
            print(f"created {kind} index '{name}' (takes ~1 minute to build)")
    except OperationFailure as exc:
        print(f"could not create {kind} index '{name}' (needs an Atlas cluster): {exc}")

if __name__ == "__main__":
    main()
