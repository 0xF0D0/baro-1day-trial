from urllib.parse import urlsplit, urlunsplit

from model import MapError, MappedRun, Row, Scope

SOURCE = "google_results"
ENDING = {("search_rankings", "search_result"): "absent"}

ADS = Scope("ads", "could_not_look",
            "ads are not collected: no tested Actor returned the ads a person saw for the same term")
NOT_FETCHED = ("missing", "actor_error", "no_organic_results")


def _url_key(url: str) -> str:
    parts = urlsplit(url)
    query = "&".join(p for p in parts.query.split("&") if p.split("=", 1)[0] != "srsltid")
    return urlunsplit(parts._replace(query=query))


def _domain(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"no host in {url!r}")
    return host.removeprefix("www.")


def _is_google_link(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.hostname or "").lower().removeprefix("www.") == "google.com" and parts.path == "/search"


def _rows(rec: dict) -> tuple[list[Row], int]:
    raw, term = rec["raw"], rec["key"]
    rank = raw["keyword_index"]
    if not isinstance(rank, int) or isinstance(rank, bool):
        raise ValueError(f"keyword_index is not an integer: {rank!r}")
    rows, seen, skipped = [], set(), 0
    for res in raw["serp"]["organicResults"]:
        if _is_google_link(res["url"]):
            skipped += 1
            continue
        url_key = _url_key(res["url"])
        if url_key in seen:
            continue
        seen.add(url_key)
        position = res["position"]
        if not isinstance(position, int) or isinstance(position, bool):
            raise ValueError(f"position is not an integer: {position!r}")
        columns = {"keyword": term, "keyword_rank": rank, "position": position - skipped, "result_url": res["url"],
                   "domain": _domain(res["url"]), "title": res.get("title"),
                   "description": res.get("description"), "result_type": res.get("type")}
        rows.append(Row("search_rankings", "search_result", f"{term}|{url_key}", term, rec["url"],
                        rec["fetched_at"], raw, columns))
    return rows, skipped


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows, scopes, not_fetched = [], [], 0
    for rec in records:
        key = rec.get("key")
        if rec.get("kind") != "search_results_page":
            raise MapError(f"{key}: unknown record kind {rec.get('kind')!r}")
        try:
            error = rec["raw"]["error"]
            if error is None:
                got, skipped = _rows(rec)
                if got:
                    rows.extend(got)
                    scopes.append(Scope(key, "ok", ""))
                elif skipped:
                    not_fetched += 1
                    scopes.append(Scope(key, "could_not_look", "no_organic_results"))
                else:
                    raise ValueError("fetched page has no organic results")
            elif error in NOT_FETCHED:
                not_fetched += 1
                scopes.append(Scope(key, "could_not_look", error))
            else:
                raise ValueError(f"unknown error state {error!r}")
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            raise MapError(f"{key}: {type(e).__name__}: {e}") from e
    scopes.append(ADS)
    if not records:
        scopes.append(Scope("all", run["status"], run["reason"]))
    return MappedRun(rows, scopes, not_fetched)
