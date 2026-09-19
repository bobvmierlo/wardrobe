"""Looking up a place, and asking what the weather is doing there.

Both go through the server rather than the browser. The app's own
Content-Security-Policy is ``connect-src 'self'``, so a page that called a
weather service directly would be blocked — and this way one fetch serves
every device in the house, and no third party is handed the coordinates of
everybody's home by their browser.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import weather as weather_service
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..preferences import as_weather_out, forecast_for, get_preferences
from ..schemas import PlaceOut, WeatherOut
from ..tags import WEATHER_TAGS

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/tags", response_model=list[str])
def tags(_: User = Depends(get_current_user)):
    """The weather vocabulary garments and outfits are tagged with."""
    return WEATHER_TAGS


@router.get("/search", response_model=list[PlaceOut])
def search(
    q: str = Query(min_length=1, max_length=120),
    _: User = Depends(get_current_user),
):
    """Find a place by name or postcode, to fetch the forecast for."""
    try:
        places = weather_service.search_places(q)
    except weather_service.WeatherUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [
        PlaceOut(
            name=p.name,
            label=p.label,
            latitude=p.latitude,
            longitude=p.longitude,
            region=p.region,
            country=p.country,
            postcode=p.postcode,
        )
        for p in places
    ]


@router.get("/lookup", response_model=PlaceOut)
def lookup(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    _: User = Depends(get_current_user),
):
    """Name the coordinates the browser just handed us.

    After someone grants the location permission all the app has is a pair of
    numbers, and "52.09, 5.12" is not something to show on a screen. A failure
    here is not an error: the coordinates still work, they just stay unnamed.
    """
    label = f"{latitude:.2f}, {longitude:.2f}"
    try:
        forecast = weather_service.current(latitude, longitude)
        label = forecast.location or label
    except weather_service.WeatherUnavailable:
        pass
    return PlaceOut(
        name=label, label=label, latitude=latitude, longitude=longitude
    )


@router.get("/current", response_model=WeatherOut)
def current(
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    label: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The weather, for given coordinates or for whatever this user saved."""
    if latitude is not None and longitude is not None:
        try:
            forecast = weather_service.current(latitude, longitude, label)
        except weather_service.WeatherUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return as_weather_out(forecast, "auto")

    prefs = get_preferences(db, user)
    forecast = forecast_for(prefs)
    if forecast is None:
        raise HTTPException(
            status_code=404,
            detail="Nog geen locatie ingesteld — kies er een bij Instellingen.",
        )
    return as_weather_out(forecast, prefs.weather_mode or "auto")
