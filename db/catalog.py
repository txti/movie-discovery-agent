import ast

import numpy as np
import pandas as pd
from huggingface_hub import hf_hub_download

CATALOG_REPO = "Chelikani2006/Movie-recommendation-data"
CATALOG_FILE = "movies_expanded_2018_2026.csv"
STREAMERS = ["Netflix", "Hulu", "Prime Video", "Disney+"]
MIN_VOTES = 10
PRIOR_VOTES = 500


def fetch(repo: str, path: str) -> str:
    return hf_hub_download(repo, path, repo_type="dataset")


def load_raw() -> pd.DataFrame:
    return pd.read_csv(fetch(CATALOG_REPO, CATALOG_FILE), low_memory=False)


def parse_names(value: object, key: str = "name") -> list[str]:
    """Legacy rows hold Python-literal lists of dicts; 2018+ rows hold comma-separated names."""
    if not isinstance(value, str) or not value.strip():
        return []
    if value.lstrip().startswith("["):
        return [d[key] for d in ast.literal_eval(value)]
    return [v.strip() for v in value.split(",") if v.strip()]


def is_placeholder(text: pd.Series) -> pd.Series:
    return text.fillna("").str.strip().str.lower().str.match(r"^(no (movie )?overview.*)?$")


def embed_text(r: pd.Series) -> str:
    head = f"{r.title} ({r.year})" if pd.notna(r.year) else r.title
    genres = f"Genres: {', '.join(r.genres)}." if r.genres else ""
    tagline = r.tagline if isinstance(r.tagline, str) else ""
    overview = r.overview if isinstance(r.overview, str) else ""
    return " ".join(p for p in [f"{head}.", genres, tagline, overview] if p)


def build_catalog(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({
        "tmdb_id": raw.id,
        "imdb_id": raw.imdb_id,
        "title": raw.title.str.strip(),
        "year": pd.to_datetime(raw.release_date, errors="coerce").dt.year.astype("Int64"),
        "genres": raw.genres.map(parse_names),
        "overview": raw.overview.str.strip().mask(is_placeholder(raw.overview)),
        "tagline": raw.tagline.str.strip(),
        "director": raw.director.map(parse_names),
        "cast": raw.main_cast.map(lambda s: parse_names(s)[:3]),
        "collection": raw.belongs_to_collection.map(lambda s: ast.literal_eval(s)["name"] if isinstance(s, str) else None),
        "language": raw.original_language,
        "runtime": raw.runtime.where(raw.runtime > 0),
        "vote_average": raw.vote_average,
        "vote_count": raw.vote_count.astype(int),
        "streaming": raw[STREAMERS].apply(lambda r: [s for s in STREAMERS if r[s]], axis=1),
        "poster_path": raw.poster_path,
    })
    prior = np.average(df.vote_average, weights=df.vote_count)
    df["weighted_rating"] = ((df.vote_count * df.vote_average + PRIOR_VOTES * prior) / (df.vote_count + PRIOR_VOTES)).round(3)
    df["indexable"] = raw.status.eq("Released") & raw.adult.ne(1) & df.overview.notna() & df.vote_count.ge(MIN_VOTES)
    df["embed_text"] = df.apply(embed_text, axis=1)
    return df
