from functools import cache
from pathlib import Path

import chromadb
import numpy as np
import pandas as pd
from fastembed import TextEmbedding

from agent.catalog import build_catalog, load_raw

INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "chroma"
COLLECTION = "movies"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
BATCH = 2000
CANDIDATES = 300
RATING_WEIGHT = 1.0
METADATA = [
    "title", "year", "genres", "overview", "director", "cast", "collection", "language", "runtime",
    "vote_average", "vote_count", "weighted_rating", "streaming", "poster_path", "imdb_id",
]


@cache
def embedder() -> TextEmbedding:
    return TextEmbedding(EMBED_MODEL)


def present(value: object) -> bool:
    return bool(value) if isinstance(value, list) else pd.notna(value)


def build(col: chromadb.Collection) -> None:
    catalog = build_catalog(load_raw())
    catalog = catalog[catalog.indexable]
    done = set(col.get(include=[])["ids"])
    todo = catalog[~catalog.tmdb_id.astype(str).isin(done)]
    todo = todo.iloc[todo.embed_text.str.len().argsort()]
    for start in range(0, len(todo), BATCH):
        part = todo.iloc[start:start + BATCH]
        col.add(
            ids=part.tmdb_id.astype(str).tolist(),
            embeddings=list(embedder().embed(part.embed_text.tolist(), batch_size=64)),
            documents=part.embed_text.tolist(),
            metadatas=[{k: v for k in METADATA if present(v := r[k])} for r in part.to_dict("records")],
        )
        print(f"indexed {len(done) + start + len(part)}/{len(catalog)}")
    col.modify(metadata={"complete": True})


@cache
def collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    col = client.get_or_create_collection(COLLECTION, configuration={"hnsw": {"space": "cosine"}}, embedding_function=None)
    if not (col.metadata or {}).get("complete"):
        build(col)
    return col


@cache
def movies() -> pd.DataFrame:
    col = collection()
    pages = [col.get(include=["metadatas"], limit=BATCH, offset=start) for start in range(0, col.count(), BATCH)]
    return pd.DataFrame(
        [m for p in pages for m in p["metadatas"]], columns=METADATA,
    ).assign(tmdb_id=[int(i) for p in pages for i in p["ids"]])


def find_movie(title: str, year: int | None = None) -> int | None:
    m = movies()
    hit = m[(m.title.str.lower() == title.strip().lower()) & (year is None or m.year == year)]
    return None if hit.empty else int(hit.loc[hit.vote_count.idxmax(), "tmdb_id"])


def movie_vectors(tmdb_ids: list[int]) -> np.ndarray:
    return np.asarray(collection().get(ids=[str(i) for i in dict.fromkeys(tmdb_ids)], include=["embeddings"])["embeddings"])


def where_clause(
    genres: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    runtime_max: int | None = None,
    language: str | None = None,
    director: str | None = None,
    cast: str | None = None,
) -> dict | None:
    conds = [{"genres": {"$contains": g}} for g in genres or []]
    for key, op, value in [
        ("year", "$gte", year_min), ("year", "$lte", year_max), ("runtime", "$lte", runtime_max),
        ("language", "$eq", language), ("director", "$contains", director), ("cast", "$contains", cast),
    ]:
        if value is not None:
            conds.append({key: {op: value}})
    return {"$and": conds} if len(conds) > 1 else (conds[0] if conds else None)


def candidates(embedding: np.ndarray, where: dict | None, n: int = CANDIDATES) -> pd.DataFrame:
    res = collection().query(query_embeddings=[embedding], n_results=n, where=where, include=["metadatas", "distances"])
    hits = pd.DataFrame(res["metadatas"][0], columns=METADATA)
    hits.insert(0, "tmdb_id", [int(i) for i in res["ids"][0]])
    hits["similarity"] = 1 - np.asarray(res["distances"][0])
    return hits


def rerank(hits: pd.DataFrame, weight: float = RATING_WEIGHT) -> pd.DataFrame:
    scored = hits.assign(score=hits.similarity + weight * hits.weighted_rating / 10)
    return scored.sort_values("score", ascending=False, ignore_index=True)


def search(query: str = "", like: list[int] | None = None, k: int = 10, **filters) -> pd.DataFrame:
    """Semantic search over the catalog. `like` holds tmdb_ids whose vectors are averaged with the query."""
    like = like or []
    vectors = list(movie_vectors(like)) if like else []
    if query:
        vectors.append(next(embedder().embed([QUERY_PREFIX + query])))
    if not vectors:
        raise ValueError("search needs a query or at least one liked movie")
    hits = candidates(np.mean(vectors, axis=0), where_clause(**filters), CANDIDATES + len(like))
    return rerank(hits[~hits.tmdb_id.isin(like)]).head(k)


if __name__ == "__main__":
    cols = ["title", "year", "genres", "runtime", "weighted_rating", "similarity"]
    hits = search("psychological thriller with a dark, suspenseful story", genres=["Thriller"], year_min=2015, runtime_max=120)
    print(hits[cols].to_string())
    assert len(hits) and hits.genres.map(lambda g: "Thriller" in g).all()
    assert (hits.year >= 2015).all() and (hits.runtime <= 120).all()

    inception = find_movie("inception")
    hits = search(like=[inception])
    print(hits[cols].to_string())
    assert inception not in hits.tmdb_id.values
    assert search("zzz", year_min=3000).empty
