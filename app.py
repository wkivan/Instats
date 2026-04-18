from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import requests

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY = "d8816fc522msha1fbd9fec121d80p1c7333jsn745e1baa7ae7"
RAPIDAPI_HOST = "starapi1.p.rapidapi.com"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json"
}

BASE_URL = f"https://{RAPIDAPI_HOST}"


def get_user_info(username):
    try:
        res = requests.post(
            f"{BASE_URL}/instagram/user/get_web_profile_info",
            headers=HEADERS,
            json={"username": username},
            timeout=15
        )
        data = res.json()
        user_obj = (
            data
            .get("response", {})
            .get("body", {})
            .get("data", {})
            .get("user", {})
        )
        uid = user_obj.get("id") or user_obj.get("pk")
        return uid, user_obj
    except Exception as e:
        print(f"❌ Error obteniendo user_id: {e}")
        return None, None


def get_clips(user_id):
    posts = []
    end_cursor = None

    for page in range(10):
        try:
            body = {"id": int(user_id), "count": 12}
            if end_cursor:
                body["end_cursor"] = end_cursor

            res = requests.post(
                f"{BASE_URL}/instagram/user/get_clips",
                headers=HEADERS,
                json=body,
                timeout=15
            )
            data = res.json()
            print(f"📡 clips page {page+1} status: {res.status_code}")

            body_data = data.get("response", {}).get("body", {})
            items = (
                body_data.get("items") or
                data.get("items") or
                (data.get("data") or {}).get("items") or
                []
            )

            if not items:
                break

            for item in items:
                media = item.get("media") or item

                thumb = ""
                if media.get("image_versions2"):
                    candidates = media["image_versions2"].get("candidates", [])
                    if candidates:
                        thumb = candidates[0].get("url", "")
                elif media.get("thumbnail_url"):
                    thumb = media["thumbnail_url"]

                taken_at = media.get("taken_at") or media.get("timestamp") or 0
                if isinstance(taken_at, int) and taken_at > 0:
                    date_str = datetime.utcfromtimestamp(taken_at).strftime("%Y-%m-%d %H:%M:%S")
                    weekday = datetime.utcfromtimestamp(taken_at).strftime("%A")
                    hour = datetime.utcfromtimestamp(taken_at).hour
                else:
                    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    weekday = ""
                    hour = 0

                caption = ""
                cap_obj = media.get("caption")
                if isinstance(cap_obj, dict):
                    caption = cap_obj.get("text", "")[:150]
                elif isinstance(cap_obj, str):
                    caption = cap_obj[:150]

                code = media.get("code") or media.get("shortcode") or ""
                likes = media.get("like_count") or media.get("likes") or 0
                views = media.get("play_count") or media.get("view_count") or media.get("views") or 0
                comments = media.get("comment_count") or media.get("comments") or 0
                engagement = round((likes / views * 100), 2) if views > 0 else 0

                posts.append({
                    "shortcode": code,
                    "likes": likes,
                    "views": views,
                    "comments": comments,
                    "engagement": engagement,
                    "date": date_str,
                    "weekday": weekday,
                    "hour": hour,
                    "caption": caption,
                    "thumbnail": thumb,
                    "post_url": f"https://www.instagram.com/reel/{code}/" if code else "",
                })

            page_info = body_data.get("page_info") or data.get("page_info") or {}
            if page_info.get("has_next_page"):
                end_cursor = page_info.get("end_cursor")
            else:
                break

        except Exception as e:
            print(f"❌ Error en página {page+1}: {e}")
            break

    return posts


@app.route("/analyze", methods=["GET"])
def analyze():
    username = request.args.get("username", "").strip().lstrip("@")
    period = request.args.get("period", "all")
    sort_by = request.args.get("sort", "views")
    min_views = int(request.args.get("min_views", 0))
    min_likes = int(request.args.get("min_likes", 0))

    if not username:
        return jsonify({"error": "Falta el parámetro 'username'"}), 400

    print(f"\n🔍 Buscando: {username}")
    user_id, user_obj = get_user_info(username)

    if not user_id:
        return jsonify({"error": f"No se encontró el usuario '{username}'"}), 400

    print(f"✅ user_id: {user_id}")

    posts = get_clips(user_id)
    print(f"✅ {len(posts)} videos obtenidos")

    if not posts:
        return jsonify({"error": "No se encontraron videos para este perfil"}), 404

    # Filtro de tiempo
    now = datetime.utcnow()
    if period == "1m":
        cutoff = now - timedelta(days=30)
    elif period == "3m":
        cutoff = now - timedelta(days=90)
    elif period == "6m":
        cutoff = now - timedelta(days=180)
    elif period == "1y":
        cutoff = now - timedelta(days=365)
    else:
        cutoff = datetime(2000, 1, 1)

    filtered = []
    for p in posts:
        try:
            d = datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
            if d >= cutoff and p["views"] >= min_views and p["likes"] >= min_likes:
                filtered.append(p)
        except Exception:
            filtered.append(p)

    if not filtered:
        return jsonify({"error": f"No hay videos con los filtros aplicados"}), 404

    # Ordenar
    if sort_by == "engagement":
        sorted_posts = sorted(filtered, key=lambda x: x["engagement"], reverse=True)
    elif sort_by == "likes":
        sorted_posts = sorted(filtered, key=lambda x: x["likes"], reverse=True)
    elif sort_by == "comments":
        sorted_posts = sorted(filtered, key=lambda x: x["comments"], reverse=True)
    else:
        sorted_posts = sorted(filtered, key=lambda x: x["views"], reverse=True)

    # Análisis: mejor día y hora
    from collections import Counter
    weekday_counts = Counter(p["weekday"] for p in filtered if p["weekday"])
    hour_counts = Counter(p["hour"] for p in filtered)
    best_day = weekday_counts.most_common(1)[0][0] if weekday_counts else "N/A"
    best_hour = hour_counts.most_common(1)[0][0] if hour_counts else "N/A"

    # Stats generales
    total_views = sum(p["views"] for p in filtered)
    total_likes = sum(p["likes"] for p in filtered)
    avg_views = round(total_views / len(filtered)) if filtered else 0
    avg_likes = round(total_likes / len(filtered)) if filtered else 0
    avg_engagement = round(sum(p["engagement"] for p in filtered) / len(filtered), 2) if filtered else 0

    # Datos para gráfico (todos los filtrados ordenados por fecha)
    chart_data = sorted(filtered, key=lambda x: x["date"])

    # Info del perfil
    profile_info = {
        "username": user_obj.get("username", username),
        "full_name": user_obj.get("full_name", ""),
        "biography": user_obj.get("biography", ""),
        "followers": (user_obj.get("edge_followed_by") or {}).get("count", 0),
        "following": (user_obj.get("edge_follow") or {}).get("count", 0),
        "profile_pic": user_obj.get("profile_pic_url_hd") or user_obj.get("profile_pic_url", ""),
        "is_verified": user_obj.get("is_verified", False),
    }

    return jsonify({
        "profile": profile_info,
        "stats": {
            "total_videos": len(posts),
            "filtered_videos": len(filtered),
            "avg_views": avg_views,
            "avg_likes": avg_likes,
            "avg_engagement": avg_engagement,
            "best_day": best_day,
            "best_hour": f"{best_hour}:00" if isinstance(best_hour, int) else best_hour,
        },
        "chart_data": [{"date": p["date"][:10], "views": p["views"], "likes": p["likes"]} for p in chart_data],
        "posts": sorted_posts[:20]
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)