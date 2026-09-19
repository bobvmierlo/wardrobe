"""Each person's own settings, and the forecast that follows from them.

Everything here is per user rather than per wardrobe. Two people sharing a kast
can want a different colour scheme, live in different places, and disagree
about whether the app should keep a record of what they wore — so none of it
belongs on the kast they share.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import weather as weather_service
from .config import settings
from .models import StyleProfile, User, UserPreference
from .schemas import PreferencesOut, WeatherOut
from .tags import split_tags

#: What a brand-new account gets. The wear log is deliberately off: recording
#: what somebody wore is a thing to opt into, not a default they discover.
DEFAULT_THEME = "midnight"


def get_preferences(db: Session, user: User) -> UserPreference:
    """This user's preferences, created on first read."""
    prefs = db.get(UserPreference, user.id)
    if prefs is None:
        prefs = UserPreference(user_id=user.id, theme=DEFAULT_THEME)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def get_profile(db: Session, user: User) -> StyleProfile:
    """This user's stijl-DNA, created on first read."""
    profile = db.get(StyleProfile, user.id)
    if profile is None:
        profile = StyleProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def serialize(prefs: UserPreference) -> PreferencesOut:
    return PreferencesOut(
        theme=prefs.theme or DEFAULT_THEME,
        wear_log_enabled=bool(prefs.wear_log_enabled),
        location_label=prefs.location_label,
        latitude=prefs.latitude,
        longitude=prefs.longitude,
        weather_mode=prefs.weather_mode or "auto",
        manual_weather=split_tags(prefs.manual_weather),
        weather_available=settings.weather_enabled,
    )


def forecast_for(prefs: UserPreference) -> weather_service.Forecast | None:
    """The weather this user should be shown, or None when they set none.

    Never raises: a wardrobe screen that cannot paint because a weather service
    is down would be a poor trade. The caller gets ``None`` and says so.
    """
    if (prefs.weather_mode or "auto") == "manual":
        tags = split_tags(prefs.manual_weather)
        if not tags:
            return None
        return weather_service.manual_forecast(tags)

    if prefs.latitude is None or prefs.longitude is None:
        return None
    try:
        return weather_service.current(
            prefs.latitude, prefs.longitude, prefs.location_label or ""
        )
    except weather_service.WeatherUnavailable:
        return None


def as_weather_out(
    forecast: weather_service.Forecast | None, mode: str = "auto"
) -> WeatherOut | None:
    if forecast is None:
        return None
    return WeatherOut(
        location=forecast.location,
        description=forecast.description,
        temperature=round(forecast.temperature, 1),
        apparent_temperature=round(forecast.apparent_temperature, 1),
        wind_speed=round(forecast.wind_speed, 1),
        precipitation=round(forecast.precipitation, 1),
        precipitation_chance=forecast.precipitation_chance,
        high=None if forecast.high is None else round(forecast.high, 1),
        low=None if forecast.low is None else round(forecast.low, 1),
        is_day=forecast.is_day,
        tags=forecast.tags,
        mode=mode,
    )


def weather_tags_for(prefs: UserPreference) -> list[str]:
    """Just the tags, for the recommendation engine."""
    forecast = forecast_for(prefs)
    return list(forecast.tags) if forecast else []


def daily_forecast_for(prefs: UserPreference, days: int = 7):
    """The week's outlook for this user's location, or ``[]`` when there is none.

    Like :func:`forecast_for` this never raises: a planner that will not paint
    because a weather service is unreachable is worse than a planner with no
    little sun icons on it.
    """
    if (prefs.weather_mode or "auto") == "manual":
        return []
    if prefs.latitude is None or prefs.longitude is None:
        return []
    try:
        return weather_service.daily(prefs.latitude, prefs.longitude, days)
    except weather_service.WeatherUnavailable:
        return []


def day_as_weather_out(day) -> WeatherOut:
    """One day of the outlook, in the shape the API uses everywhere else."""
    return WeatherOut(
        location="",
        description=day.description,
        temperature=round(day.high if day.high is not None else 0.0, 1),
        apparent_temperature=round(day.high if day.high is not None else 0.0, 1),
        wind_speed=round(day.wind_speed, 1),
        precipitation=0.0,
        precipitation_chance=day.precipitation_chance,
        high=None if day.high is None else round(day.high, 1),
        low=None if day.low is None else round(day.low, 1),
        tags=day.tags,
        mode="auto",
    )
