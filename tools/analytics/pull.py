"""Free daily analytics for the Tridev channels, straight from the official APIs.

Replaces paid connectors (Windsor) for: YouTube (AMM, YugYogii), Facebook Pages and
linked Instagram accounts (Mira Noir, YugYogi). AMM's Instagram stays on FavStash.

Every source is optional: a missing secret skips that source, and a failing metric is
recorded in `errors` instead of stopping the run. Output:
  data/analytics/YYYY-MM-DD.json   full pull (IST date)
  data/analytics/latest.md         short human summary the morning huddle reads first

Secrets (GitHub Actions -> Settings -> Secrets and variables -> Actions):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  YT_REFRESH_TOKEN_AMM, YT_REFRESH_TOKEN_YUGYOGII
  META_PAGE_TOKEN_MIRA, META_PAGE_TOKEN_YUGYOGI
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

import requests

GRAPH = "https://graph.facebook.com/v25.0"
YTA = "https://youtubeanalytics.googleapis.com/v2/reports"
YTD = "https://www.googleapis.com/youtube/v3"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TIMEOUT = 60

YOUTUBE = {"amm": "YT_REFRESH_TOKEN_AMM", "yugyogii": "YT_REFRESH_TOKEN_YUGYOGII"}
META = {"mira-noir": "META_PAGE_TOKEN_MIRA", "yugyogii": "META_PAGE_TOKEN_YUGYOGI"}

YT_METRICS = [
    "views", "engagedViews", "estimatedMinutesWatched", "averageViewDuration",
    "averageViewPercentage", "likes", "comments", "shares",
    "subscribersGained", "subscribersLost",
]
PAGE_METRICS = ["page_impressions_unique", "page_post_engagements", "page_video_views",
                "page_daily_follows_unique", "page_views_total"]
IG_ACCOUNT_METRICS = ["reach", "views", "total_interactions", "accounts_engaged",
                      "likes", "comments", "shares", "saves", "follows_and_unfollows"]
IG_MEDIA_METRICS = ["reach", "views", "saved", "shares", "total_interactions",
                    "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def secret(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


# ---------- YouTube ----------

def google_access_token(refresh_token: str) -> str:
    r = requests.post("https://oauth2.googleapis.com/token", timeout=TIMEOUT, data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def yt_report(token: str, start: str, end: str, metrics: list[str], **extra) -> dict:
    params = {"ids": "channel==MINE", "startDate": start, "endDate": end,
              "metrics": ",".join(metrics), **extra}
    r = requests.get(YTA, params=params, timeout=TIMEOUT,
                     headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 400 and "engagedViews" in metrics:
        # Older API surfaces may not accept engagedViews; retry without it.
        return yt_report(token, start, end, [m for m in metrics if m != "engagedViews"], **extra)
    r.raise_for_status()
    body = r.json()
    cols = [h["name"] for h in body.get("columnHeaders", [])]
    return {"columns": cols, "rows": body.get("rows", [])}


def pull_youtube(refresh_token: str, today: dt.date) -> dict:
    out: dict = {"errors": []}
    token = google_access_token(refresh_token)
    h = {"Authorization": f"Bearer {token}"}

    ch = requests.get(f"{YTD}/channels", headers=h, timeout=TIMEOUT,
                      params={"part": "snippet,statistics", "mine": "true"}).json()
    item = (ch.get("items") or [{}])[0]
    out["channel"] = {"id": item.get("id"), "title": item.get("snippet", {}).get("title"),
                      **{k: int(v) for k, v in item.get("statistics", {}).items() if isinstance(v, str) and v.isdigit()}}

    end = (today - dt.timedelta(days=1)).isoformat()  # YouTube Analytics lags ~1-2 days
    windows = {"last_7d": 7, "prior_7d": 14, "last_28d": 28}
    for name, days in windows.items():
        start = (today - dt.timedelta(days=days)).isoformat()
        stop = end if name != "prior_7d" else (today - dt.timedelta(days=8)).isoformat()
        try:
            out[name] = yt_report(token, start, stop, YT_METRICS)
        except requests.HTTPError as e:
            out["errors"].append(f"{name}: {e.response.status_code} {e.response.text[:200]}")

    try:
        start = (today - dt.timedelta(days=28)).isoformat()
        out["daily_28d"] = yt_report(token, start, end, YT_METRICS, dimensions="day", sort="day")
        top = yt_report(token, start, end, YT_METRICS, dimensions="video",
                        sort="-views", maxResults="25")
        ids = [row[0] for row in top["rows"]]
        if ids:
            vids = requests.get(f"{YTD}/videos", headers=h, timeout=TIMEOUT, params={
                "part": "snippet,contentDetails", "id": ",".join(ids)}).json()
            meta = {v["id"]: {"title": v["snippet"]["title"],
                              "published": v["snippet"]["publishedAt"],
                              "duration": v["contentDetails"]["duration"]}
                    for v in vids.get("items", [])}
            top["video_meta"] = meta
        out["top_videos_28d"] = top
    except requests.HTTPError as e:
        out["errors"].append(f"videos: {e.response.status_code} {e.response.text[:200]}")
    return out


# ---------- Meta (Facebook Page + linked Instagram) ----------

def graph_get(path: str, token: str, **params) -> dict:
    r = requests.get(f"{GRAPH}/{path}", timeout=TIMEOUT,
                     params={"access_token": token, **params})
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"]))[:200])
    return body


def pull_meta(token: str, today: dt.date) -> dict:
    out: dict = {"errors": []}
    page = graph_get("me", token, fields="id,name,followers_count,fan_count,"
                     "instagram_business_account{id,username,followers_count,media_count}")
    out["page"] = {k: page.get(k) for k in ("id", "name", "followers_count", "fan_count")}
    since = int(dt.datetime.combine(today - dt.timedelta(days=28), dt.time(), IST).timestamp())
    until = int(dt.datetime.combine(today, dt.time(), IST).timestamp())

    out["page_insights"] = {}
    for m in PAGE_METRICS:  # one call per metric so a retired metric can't sink the rest
        try:
            data = graph_get(f"{page['id']}/insights", token, metric=m, period="day",
                             since=since, until=until)["data"]
            out["page_insights"][m] = data[0]["values"] if data else []
        except RuntimeError as e:
            out["errors"].append(f"page {m}: {e}")

    ig = page.get("instagram_business_account")
    if not ig:
        return out
    out["instagram"] = {"account": ig, "insights_7d": {}, "insights_prior_7d": {}, "media": []}
    for label, a, b in (("insights_7d", 7, 0), ("insights_prior_7d", 14, 7)):
        s = int(dt.datetime.combine(today - dt.timedelta(days=a), dt.time(), IST).timestamp())
        u = int(dt.datetime.combine(today - dt.timedelta(days=b), dt.time(), IST).timestamp())
        for m in IG_ACCOUNT_METRICS:
            try:
                data = graph_get(f"{ig['id']}/insights", token, metric=m, period="day",
                                 metric_type="total_value", since=s, until=u)["data"]
                out["instagram"][label][m] = data[0].get("total_value", {}).get("value") if data else None
            except RuntimeError as e:
                out["errors"].append(f"ig {label} {m}: {e}")

    media = graph_get(f"{ig['id']}/media", token, limit=25, fields=(
        "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"))
    for item in media.get("data", []):
        item["caption"] = (item.get("caption") or "")[:120]
        item["insights"] = {}
        for m in IG_MEDIA_METRICS:
            if m.startswith("ig_reels") and item.get("media_product_type") != "REELS":
                continue
            try:
                data = graph_get(f"{item['id']}/insights", token, metric=m)["data"]
                item["insights"][m] = data[0]["values"][0]["value"] if data else None
            except RuntimeError:
                pass  # metric not offered for this media type
        out["instagram"]["media"].append(item)
    return out


# ---------- summary ----------

def yt_line(name: str, d: dict) -> str:
    def total(block: str, col: str):
        b = d.get(block) or {}
        if col in b.get("columns", []) and b.get("rows"):
            return b["rows"][0][b["columns"].index(col)]
        return "n/a"
    ch = d.get("channel", {})
    return (f"- **YouTube {name}**: {ch.get('subscriberCount', '?')} subs, {ch.get('videoCount', '?')} videos | "
            f"7d views {total('last_7d', 'views')} (prior {total('prior_7d', 'views')}), "
            f"engaged {total('last_7d', 'engagedViews')}, min watched {total('last_7d', 'estimatedMinutesWatched')}, "
            f"avg % viewed {total('last_7d', 'averageViewPercentage')}, "
            f"subs +{total('last_7d', 'subscribersGained')}/-{total('last_7d', 'subscribersLost')}")


def meta_lines(name: str, d: dict) -> list[str]:
    p = d.get("page", {})
    lines = [f"- **Facebook {name}**: {p.get('followers_count', '?')} followers"]
    ig = d.get("instagram")
    if ig:
        a, cur, prev = ig["account"], ig["insights_7d"], ig["insights_prior_7d"]
        lines.append(f"- **Instagram {name}** (@{a.get('username')}): {a.get('followers_count')} followers | "
                     f"7d reach {cur.get('reach')} (prior {prev.get('reach')}), views {cur.get('views')}, "
                     f"interactions {cur.get('total_interactions')}, shares {cur.get('shares')}, saves {cur.get('saves')}")
    return lines


def main() -> int:
    today = dt.datetime.now(IST).date()
    result: dict = {"date_ist": today.isoformat(), "youtube": {}, "meta": {}, "skipped": [], "failed": []}

    google_ready = secret("GOOGLE_CLIENT_ID") and secret("GOOGLE_CLIENT_SECRET")
    for name, env in YOUTUBE.items():
        tok = secret(env)
        if not (tok and google_ready):
            result["skipped"].append(f"youtube {name} (no {env} or Google client)")
            continue
        try:
            result["youtube"][name] = pull_youtube(tok, today)
        except Exception as e:  # keep going for the other channels
            result["failed"].append(f"youtube {name}: {e}")

    for name, env in META.items():
        tok = secret(env)
        if not tok:
            result["skipped"].append(f"meta {name} (no {env})")
            continue
        try:
            result["meta"][name] = pull_meta(tok, today)
        except Exception as e:
            result["failed"].append(f"meta {name}: {e}")

    out_dir = pathlib.Path("data/analytics")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{today.isoformat()}.json").write_text(json.dumps(result, indent=1, default=str))

    lines = [f"# Analytics {today.isoformat()} (IST, official APIs; YouTube lags ~1-2 days)", ""]
    for name, d in result["youtube"].items():
        lines.append(yt_line(name, d))
    for name, d in result["meta"].items():
        lines.extend(meta_lines(name, d))
    if result["skipped"]:
        lines += ["", "Skipped (secret not set): " + "; ".join(result["skipped"])]
    if result["failed"]:
        lines += ["", "FAILED: " + "; ".join(result["failed"])]
    errs = [f"{k}/{n}: {e}" for k in ("youtube", "meta") for n, d in result[k].items() for e in d.get("errors", [])]
    if errs:
        lines += ["", "Metric errors: " + "; ".join(errs[:15])]
    lines += ["", "AMM Instagram: use FavStash (not in this pull)."]
    (out_dir / "latest.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    # A failed source is reported, not fatal; the huddle falls back to Windsor/FavStash for it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
