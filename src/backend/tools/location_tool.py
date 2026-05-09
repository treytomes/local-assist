"""
Location tool — returns current location via ip-api.com.
Checks Mara's memory for a user-set override (subject="user", predicate="location")
before making a network call, so the user can correct it by just telling Mara.
"""
import httpx


async def get_location(conn=None) -> dict:
    """
    Returns city, region, country, lat, lon, timezone, and ISP.
    If the user has stored a location override in memory, returns that instead
    and skips the network call.
    """
    # Check memory for a user-configured override first
    if conn is not None:
        try:
            from .memory_tool import search_memories_keyword
            rows = search_memories_keyword(conn, "location", limit=5)
            for row in rows:
                if row["subject"] == "user" and row["predicate"] == "location":
                    return {
                        "source": "memory",
                        "location": row["object"],
                        "note": "User-configured. To update, tell Mara your location.",
                    }
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get("http://ip-api.com/json/", params={"fields": "status,message,city,regionName,country,countryCode,lat,lon,timezone,isp"})
        data = r.json()

    if data.get("status") != "success":
        return {"error": data.get("message", "ip-api.com lookup failed")}

    return {
        "source": "ip-api.com",
        "city": data.get("city"),
        "region": data.get("regionName"),
        "country": data.get("country"),
        "country_code": data.get("countryCode"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "timezone": data.get("timezone"),
        "isp": data.get("isp"),
    }
