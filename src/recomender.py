import pickle

import numpy as np
from scipy.sparse import csr_matrix

from src.users import sync_diary
from src.db import get_user_diary_all
from src.cache import cache


with open("model/model.pkl", "rb") as f:
    obj = pickle.load(f)

model = obj["model"]
item_map = obj["item_map"]
user_map = obj["user_map"]
id_to_film = {idx: film_id for film_id, idx in item_map.items()}


def process_film_id(film_id):
    parts = film_id.split("/")
    film_id = "/".join(parts[1:3])
    return f"/{film_id}/"


def get_live_recommendations(film_ids_raw, ratings, likes, is_seed, N=10):
    valid_indices = []
    valid_mask = []

    for i, fid in enumerate(film_ids_raw):
        if fid in item_map:
            valid_indices.append(item_map[fid])
            valid_mask.append(i)

    if not valid_indices:
        return []

    ratings = ratings[valid_mask]
    likes = likes[valid_mask]

    positive_ratings = ratings[ratings > 0]
    current_user_mean = np.mean(positive_ratings) if len(positive_ratings) > 0 else 3.0
    current_user_mean = current_user_mean if not is_seed else 2.5

    unrated_proxy = current_user_mean * 0.9
    rating_proxies = np.where(ratings > 0, ratings, unrated_proxy)

    ratio_scores = rating_proxies / (current_user_mean + 1e-9)

    alpha = 40
    raw_scores = 1 + ratio_scores + (likes * 1.5)
    confidences = 1 + alpha * raw_scores

    row_indices = np.zeros(len(valid_indices))
    col_indices = np.array(valid_indices)

    user_interactions = csr_matrix(
        (confidences, (row_indices, col_indices)),
        shape=(1, model.item_factors.shape[0]),
    )

    ids, _ = model.recommend(
        userid=0,
        user_items=user_interactions,
        N=N,
        recalculate_user=True,
        filter_already_liked_items=True,
    )

    return [id_to_film[i] for i in ids]


async def compute_ranked_by_user_id(user_id: str, k: int = 1000) -> list[str]:
    await sync_diary(user_id)

    entries = await get_user_diary_all(user_id)
    if not entries:
        return []

    raw_film_ids = []
    raw_ratings = []
    raw_likes = []

    for entry in entries:
        fid = entry.get("film_id")
        if not fid:
            continue
        fid = process_film_id(fid)

        rating = entry.get("rating")
        liked = entry.get("liked", False)

        r_val = float(rating) if (rating is not None and rating > 0) else 0.0
        l_val = 1.0 if liked else 0.0

        raw_film_ids.append(fid)
        raw_ratings.append(r_val)
        raw_likes.append(l_val)

    if len(raw_film_ids) < 2:
        return []

    return get_live_recommendations(
        np.array(raw_film_ids), np.array(raw_ratings), np.array(raw_likes), False, N=k
    )


async def compute_ranked_by_seeds(seed_film_ids: list[str], k: int = 1000) -> list[str]:
    if not seed_film_ids:
        return []

    ratings = np.array([5.0] * len(seed_film_ids))
    likes = np.array([1.0] * len(seed_film_ids))

    return get_live_recommendations(np.array(seed_film_ids), ratings, likes, True, N=k)


PER_PAGE = 1000


def paginate_ranked(ranked, page: int):
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    return ranked[start:end]


async def get_ranked_cached(user_id: str, page: int):
    key = f"ranked:{user_id}"

    ranked = cache.get(key)
    if ranked is not None:
        return ("ok", paginate_ranked(ranked, page))

    ranked = await compute_ranked_by_user_id(user_id, 1000)
    if not ranked:
        return ("ok", [])

    cache.set(key, ranked)
    return ("ok", paginate_ranked(ranked, page))


async def get_ranked_by_seeds_cached(seed_film_ids: list[str], page: int):
    key = f"ranked_seeds:{'-'.join(seed_film_ids)}"

    ranked = cache.get(key)
    if ranked is not None:
        return ("ok", paginate_ranked(ranked, page))

    ranked = await compute_ranked_by_seeds(seed_film_ids, 1000)
    if not ranked:
        return ("ok", [])

    cache.set(key, ranked)
    return ("ok", paginate_ranked(ranked, page))
