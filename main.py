import asyncio

from flasgger import Swagger
from flask import Flask, jsonify, request
from flask_cors import CORS

from src.cache import cache
from src.db import init_db, close_db
from src.film import get_film_by_id
from src.get_list import get_list as fetch_list
from src.recomender import get_ranked_by_seeds_cached, get_ranked_cached
from src.search import get_film_by_name
from src.users import get_user_diary_page, get_user_favorites_handler
from src.utils import RETRY_AFTER_SECONDS

app = Flask(__name__)
swagger = Swagger(app)
cors = CORS(app)

cache.init_app(app)


RETRY_AFTER_HEADER = {"Retry-After": str(RETRY_AFTER_SECONDS)}


def _status_to_response(status, data):
    if status == "ok":
        return jsonify(data), 200
    if status == "not_found":
        return jsonify({"error": "not found"}), 404
    if status == "blocked":
        return jsonify({"error": "upstream rate-limited"}), 503, RETRY_AFTER_HEADER
    return jsonify({"error": "upstream error"}), 502


@app.route("/film/<string:id>", methods=["GET"])
async def get_film(id):
    """
    Get film details by ID
    ---
    tags:
      - Film
    parameters:
      - name: id
        in: path
        type: string
        required: true
        description: The ID of the film
    responses:
      200:
        description: Film data retrieved successfully
      404:
        description: Film not found
      503:
        description: Upstream rate-limited
    """
    key = f"film:{id}"
    cached = cache.get(key)
    if cached:
        return jsonify(cached)
    print(f"[CACHE MISS] Film details for ID: {id}", flush=True)
    status, data = await get_film_by_id(f"/film/{id}")
    if status == "ok" and data:
        cache.set(key, data)
    return _status_to_response(status, data)


@app.route("/diary/<string:user_id>", methods=["GET"])
async def get_dialy_user(user_id):
    """
    Get user diary entries
    ---
    tags:
      - Users
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
    responses:
      200:
        description: User diary data
      503:
        description: Upstream rate-limited
    """
    page = request.args.get("page", default=1, type=int)
    status, data = await get_user_diary_page(user_id, page)
    return _status_to_response(status, data)


@app.route("/favorites/<string:user_id>", methods=["GET"])
async def get_favorite_user(user_id):
    """
    Get user favorites
    ---
    tags:
      - Users
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
    responses:
      200:
        description: User favorites data
      503:
        description: Upstream rate-limited
    """
    status, data = await get_user_favorites_handler(user_id)
    return _status_to_response(status, data)


@app.route("/recommend/personalize/<string:user_id>", methods=["GET"])
async def get_recommend_user(user_id):
    """
    Get personalized recommendations for a user
    ---
    tags:
      - Recommendations
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
      - name: k
        in: query
        type: integer
        default: 1
        description: Number of recommendations to return
    responses:
      200:
        description: List of recommended films
    """
    k = request.args.get("k", default=1, type=int)
    status, data = await get_ranked_cached(user_id, k)
    return _status_to_response(status, data)


@app.route("/recommend/seed", methods=["POST"])
async def get_recommend_seed():
    """
    POST recommendations based on seed films
    ---
    tags:
      - Recommendations
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            seed_film_ids:
              type: array
              items:
                type: string
              example: ["film_1", "film_2"]
            k:
              type: integer
              default: 1
    responses:
      200:
        description: List of recommended films based on seeds
    """
    body = request.get_json()
    seed_film_ids = body.get("seed_film_ids", [])
    k = body.get("k", 1)

    status, data = await get_ranked_by_seeds_cached(seed_film_ids, k)
    return _status_to_response(status, data)


@app.route("/get_list", methods=["GET"])
async def get_list():
    """
    Fetch a list from Letterboxd
    ---
    tags:
      - Lists
    parameters:
      - name: list_url
        in: query
        type: string
        default: "https://letterboxd.com/official/list/top-250-films-with-the-most-fans"
        description: The Letterboxd film from list, actor, director, watchlist etc from url
      - name: page
        in: query
        type: integer
        description: Specific page number to fetch (returns all pages if not specified)
      - name: limit
        in: query
        type: integer
        description: Maximum number of films to return
    responses:
      200:
        description: The fetched list data
      503:
        description: Upstream rate-limited
    """
    list_url = request.args.get(
        "list_url",
        default="https://letterboxd.com/official/list/top-250-films-with-the-most-fans",
        type=str,
    )
    page = request.args.get("page", default=None, type=int)
    limit = request.args.get("limit", default=None, type=int)

    status, data = await fetch_list(list_url, page=page, limit=limit)
    return _status_to_response(status, data)


@app.route("/search", methods=["GET"])
async def search_films():
    """
    Search for films by name
    ---
    tags:
      - Film
    parameters:
      - name: query
        in: query
        type: string
        required: true
        description: The search query for the film name
    responses:
      200:
        description: List of films matching the search query
      503:
        description: Upstream rate-limited
    """
    query = request.args.get("query", default="", type=str)
    if not query:
        return jsonify([])

    key = f"search:{query}"

    cached = cache.get(key)
    if cached:
        return jsonify(cached)

    print(f"[CACHE MISS] Search query: {query}", flush=True)
    status, data = await get_film_by_name(query)
    if status == "ok" and data:
        cache.set(key, data)
    return _status_to_response(status, data)


if __name__ == "__main__":
    asyncio.run(init_db())
    app.run(debug=False, host="0.0.0.0", port=5000)
