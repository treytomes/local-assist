"""
Weather tool — current conditions + 7-day forecast via Open-Meteo (no API key required).
Calls get_location internally if lat/lon are not provided.
"""
import httpx

# WMO Weather interpretation codes → human-readable description
_WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


async def get_weather(lat: float | None = None, lon: float | None = None, conn=None) -> dict:
    """
    Returns current weather conditions and a 7-day daily forecast.
    If lat/lon are omitted, calls get_location() to determine them automatically.
    """
    location_info = {}

    if lat is None or lon is None:
        from .location_tool import get_location
        location_info = await get_location(conn)
        if "error" in location_info:
            return location_info
        lat = location_info.get("lat")
        lon = location_info.get("lon")
        if lat is None or lon is None:
            return {"error": "Could not determine location for weather lookup"}

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", "apparent_temperature", "relative_humidity_2m",
            "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m",
            "surface_pressure", "cloud_cover", "is_day",
        ],
        "daily": [
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "wind_speed_10m_max", "sunrise", "sunset",
        ],
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": location_info.get("timezone") or "auto",
        "forecast_days": 7,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
        data = r.json()

    current = data.get("current", {})
    daily = data.get("daily", {})

    def wmo(code):
        return _WMO_CODES.get(code, f"Unknown (WMO {code})")

    forecast = []
    dates = daily.get("time", [])
    for i, date in enumerate(dates):
        forecast.append({
            "date": date,
            "condition": wmo(daily["weather_code"][i]),
            "temp_high_f": daily["temperature_2m_max"][i],
            "temp_low_f": daily["temperature_2m_min"][i],
            "precipitation_in": daily["precipitation_sum"][i],
            "wind_max_mph": daily["wind_speed_10m_max"][i],
            "sunrise": daily["sunrise"][i],
            "sunset": daily["sunset"][i],
        })

    result = {
        "location": {
            "lat": lat,
            "lon": lon,
        },
        "current": {
            "condition": wmo(current.get("weather_code", 0)),
            "temp_f": current.get("temperature_2m"),
            "feels_like_f": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "precipitation_in": current.get("precipitation"),
            "wind_speed_mph": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "pressure_hpa": current.get("surface_pressure"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "is_day": bool(current.get("is_day", 1)),
        },
        "forecast": forecast,
    }

    # Attach city info if we resolved it here
    if location_info.get("city"):
        result["location"]["city"] = location_info["city"]
        result["location"]["region"] = location_info.get("region")
        result["location"]["country"] = location_info.get("country")
        result["location"]["timezone"] = location_info.get("timezone")

    return result
