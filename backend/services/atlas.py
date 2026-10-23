"""Persistence. MongoDB Atlas when MONGODB_URI is set; otherwise a local JSON store with the same interface.

Collections:
  cases          researcher, experiment, status, tags, final report (denormalised for search)
  assets         file references, checksums, versions
  analysis_runs  tool, parameters, measurements, verification for each attempt
  agent_steps    planner decisions, tool calls, errors, retries (the audit trail)
  evidence       suspicious regions, hypotheses, verification findings
  reviews        human approvals / rejections

Similar-case retrieval is hybrid: Atlas Search over failure tags (what went wrong) fused with Atlas Vector
Search over a numeric case fingerprint (what the image and baseline mask look like).
"""
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

COLLECTIONS = ["cases", "assets", "analysis_runs", "agent_steps", "evidence", "reviews"]
SEARCH_FIELDS = ["title", "notes", "researcher", "tags", "hypothesis", "report.summary"]


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


FINGERPRINT_DIM = 10


def fingerprint(stats: dict, mask: dict) -> list[float]:
    """Numeric profile of an image + its baseline mask, used for vector search over past cases.

    Each feature is squashed to [0, 1] and centred on 0 so cosine similarity separates profiles
    instead of rating every all-positive vector as near-identical.
    """
    n = max(mask["object_count"], 1)
    features = [
        math.log10(1 + max(stats["snr"], 0)) / 2,     # signal-to-noise
        stats["noise_sigma"] / 0.1,                   # camera noise
        max(stats["contrast"], 0),                    # nucleus vs background brightness
        stats["foreground_fraction"] / 0.5,           # how crowded the field is
        math.log10(n) / 3,                            # object count
        math.log10(1 + mask["median_area"]) / 4,      # typical nucleus size
        mask["area_cv"] / 2,                          # size variability (merges inflate it)
        mask["mean_solidity"],                        # concave outlines suggest merges
        mask["suspicious_regions"] / n * 3,           # share of objects flagged as merged
        mask["foreground_fraction"] / 0.5,            # mask coverage
    ]
    return [round(min(max(f, 0.0), 1.0) - 0.5, 4) for f in features]


def _cosine_rank(docs, vector, limit):
    def cos(a, b):
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0

    scored = [d | {"score": (1 + cos(d["fingerprint"], vector)) / 2} for d in docs if d.get("fingerprint")]
    return sorted(scored, key=lambda d: -d["score"])[:limit]


def _rrf(ranked_lists, limit, k=60):
    """Reciprocal rank fusion of several ranked result lists."""
    scores, docs = {}, {}
    for results in ranked_lists:
        for rank, d in enumerate(results):
            scores[d["_id"]] = scores.get(d["_id"], 0) + 1 / (k + rank + 1)
            docs[d["_id"]] = d
    order = sorted(scores, key=lambda i: -scores[i])[:limit]
    return [docs[i] | {"score": scores[i]} for i in order]


def _get_path(doc, dotted):
    for part in dotted.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


class LocalRepository:
    backend = "local-json"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = {}
        for c in COLLECTIONS:
            f = self.path / f"{c}.json"
            self._data[c] = json.loads(f.read_text()) if f.exists() else {}

    def _flush(self, coll):
        (self.path / f"{coll}.json").write_text(json.dumps(self._data[coll], indent=1))

    def insert(self, coll, doc):
        doc = {"_id": doc.get("_id") or new_id(), "created_at": now(), **doc}
        with self._lock:
            self._data[coll][doc["_id"]] = doc
            self._flush(coll)
        return doc

    def update(self, coll, _id, fields):
        with self._lock:
            self._data[coll][_id].update(fields)
            self._flush(coll)

    def get(self, coll, _id):
        return self._data[coll].get(_id)

    def delete_many(self, coll, query):
        with self._lock:
            self._data[coll] = {k: d for k, d in self._data[coll].items()
                                if not all(d.get(f) == v for f, v in query.items())}
            self._flush(coll)

    def find(self, coll, query=None, sort="created_at", descending=False, limit=0):
        query = query or {}
        docs = [d for d in self._data[coll].values() if all(d.get(k) == v for k, v in query.items())]
        docs.sort(key=lambda d: d.get(sort) or 0, reverse=descending)
        return docs[:limit] if limit else docs

    def search_cases(self, q, limit=20):
        terms = [t for t in re.split(r"\s+", q.lower()) if t]
        scored = []
        for d in self._data["cases"].values():
            text = " ".join(json.dumps(_get_path(d, f) or "") for f in SEARCH_FIELDS).lower()
            score = sum(text.count(t) for t in terms)
            if score:
                scored.append(d | {"score": score})
        scored.sort(key=lambda d: -d["score"])
        return scored[:limit], "local-keyword"

    def vector_search(self, vector, limit=10):
        return _cosine_rank(self._data["cases"].values(), vector, limit), "local-vector"

    def hybrid_search(self, q, vector, limit=10):
        text, _ = self.search_cases(q, 20)
        vec, _ = self.vector_search(vector, 20)
        return _rrf([text, vec], limit), "local-hybrid (rrf)"


class MongoRepository:
    backend = "mongodb-atlas"

    def __init__(self, uri, db_name, search_index, vector_index="ccs_vector"):
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="cell-crime-scene")
        self.db = self.client[db_name]
        self.search_index = search_index
        self.vector_index = vector_index
        self.client.admin.command("ping")
        for c in ["assets", "analysis_runs", "agent_steps", "evidence", "reviews"]:
            self.db[c].create_index([("case_id", 1), ("created_at", 1)])
        self.db.cases.create_index([("created_at", -1)])

    def insert(self, coll, doc):
        doc = {"_id": doc.get("_id") or new_id(), "created_at": now(), **doc}
        self.db[coll].insert_one(doc)
        return doc

    def update(self, coll, _id, fields):
        self.db[coll].update_one({"_id": _id}, {"$set": fields})

    def get(self, coll, _id):
        return self.db[coll].find_one({"_id": _id})

    def delete_many(self, coll, query):
        self.db[coll].delete_many(query)

    def find(self, coll, query=None, sort="created_at", descending=False, limit=0):
        cursor = self.db[coll].find(query or {}).sort(sort, -1 if descending else 1)
        return list(cursor.limit(limit) if limit else cursor)

    def search_cases(self, q, limit=20):
        """Atlas Search full-text query with fuzzy matching; regex fallback if no search index exists."""
        from pymongo.errors import OperationFailure

        try:
            results = list(self.db.cases.aggregate([
                {"$search": {"index": self.search_index,
                             "text": {"query": q, "path": SEARCH_FIELDS, "fuzzy": {"maxEdits": 1}}}},
                {"$limit": limit},
                {"$addFields": {"score": {"$meta": "searchScore"}}},
            ]))
            if results:
                return results, "atlas-search"
        except OperationFailure:
            pass
        rx = {"$regex": re.escape(q), "$options": "i"}
        results = list(self.db.cases.find({"$or": [{f: rx} for f in SEARCH_FIELDS]}).limit(limit))
        return results, "regex-fallback"

    def _text_stage(self, q):
        return {"$search": {"index": self.search_index,
                            "text": {"query": q, "path": SEARCH_FIELDS, "fuzzy": {"maxEdits": 1}}}}

    def _vector_stage(self, vector, limit):
        return {"$vectorSearch": {"index": self.vector_index, "path": "fingerprint", "queryVector": vector,
                                  "numCandidates": max(100, limit * 10), "limit": limit}}

    def vector_search(self, vector, limit=10):
        """Atlas Vector Search over case fingerprints; brute-force cosine if the index is missing."""
        from pymongo.errors import OperationFailure

        try:
            results = list(self.db.cases.aggregate([
                self._vector_stage(vector, limit),
                {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            ]))
            if results:
                return results, "atlas-vector-search"
        except OperationFailure:
            pass
        return _cosine_rank(self.db.cases.find({"fingerprint": {"$exists": True}}), vector, limit), "local-vector"

    def hybrid_search(self, q, vector, limit=10):
        """Native Atlas hybrid search ($rankFusion of $search and $vectorSearch); client-side RRF fallback."""
        from pymongo.errors import OperationFailure

        try:
            results = list(self.db.cases.aggregate([
                {"$rankFusion": {"input": {"pipelines": {
                    "text": [self._text_stage(q), {"$limit": 20}],
                    "vector": [self._vector_stage(vector, 20)],
                }}}},
                {"$limit": limit},
                {"$addFields": {"score": {"$meta": "score"}}},
            ]))
            if results:
                return results, "atlas-hybrid ($rankFusion)"
        except OperationFailure:
            pass
        text, _ = self.search_cases(q, 20)
        vec, _ = self.vector_search(vector, 20)
        return _rrf([text, vec], limit), "hybrid (client rrf)"


def make_repository(settings):
    if settings.mongodb_uri:
        return MongoRepository(settings.mongodb_uri, settings.mongodb_db, settings.atlas_search_index,
                               settings.atlas_vector_index)
    return LocalRepository(settings.storage_dir / "db")


def similar_cases(repo, case, limit=3):
    """Past investigations that ended in a verified repair, ranked by hybrid search: matching failure tags
    (Atlas Search) fused with a similar image/mask fingerprint (Atlas Vector Search)."""
    if case.get("fingerprint") and case.get("tags"):
        hits, mode = repo.hybrid_search(" ".join(case["tags"]), case["fingerprint"], limit=20)
    elif case.get("fingerprint"):
        hits, mode = repo.vector_search(case["fingerprint"], limit=20)
    elif case.get("tags"):
        hits, mode = repo.search_cases(" ".join(case["tags"]), limit=20)
    else:
        return []
    out = []
    for h in hits:
        if h["_id"] == case["_id"] or not h.get("best_attempt"):
            continue
        out.append({"case_id": h["_id"], "title": h.get("title"), "status": h.get("status"),
                    "tags": h.get("tags"), "hypothesis": h.get("hypothesis"),
                    "successful_tool": h["best_attempt"].get("tool"),
                    "successful_params": h["best_attempt"].get("params"),
                    "score": round(float(h.get("score") or 0), 4), "via": mode})
        if len(out) >= limit:
            break
    return out
