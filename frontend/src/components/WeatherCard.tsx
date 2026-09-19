import { WEATHER_ICONS, type Weather } from "../types";

interface Props {
  weather: Weather | null;
  advice?: string;
  /** Shown when there is no weather yet, e.g. "stel een locatie in". */
  empty?: React.ReactNode;
}

export function weatherIcon(tags: string[]): string {
  // The sky wins over the temperature: "it is raining" says more about what to
  // put on than "it is mild".
  for (const tag of ["Sneeuw", "Regen", "Zonnig", "Bewolkt", "Winderig"]) {
    if (tags.includes(tag)) return WEATHER_ICONS[tag];
  }
  return WEATHER_ICONS[tags[0]] ?? "🌡️";
}

/** The weather, the way the app says it out loud. */
export default function WeatherCard({ weather, advice, empty }: Props) {
  if (!weather) return <>{empty ?? null}</>;
  return (
    <div className="card weather-card">
      <div className="weather-now">
        <span className="weather-ico" aria-hidden="true">
          {weatherIcon(weather.tags)}
        </span>
        <div>
          <div className="weather-temp">{Math.round(weather.temperature)}°</div>
          <div className="muted" style={{ fontSize: "0.85rem" }}>
            {weather.description}
            {weather.location ? ` · ${weather.location}` : ""}
          </div>
        </div>
      </div>
      <div className="weather-meta muted">
        {weather.high !== null && weather.low !== null && (
          <span>
            ↑ {Math.round(weather.high)}° ↓ {Math.round(weather.low)}°
          </span>
        )}
        {/* "Feels like" is what the recommendation actually reads, so it is
            worth showing when it disagrees with the thermometer. */}
        {Math.round(weather.apparent_temperature) !== Math.round(weather.temperature) && (
          <span>voelt als {Math.round(weather.apparent_temperature)}°</span>
        )}
        {weather.precipitation_chance !== null && <span>{weather.precipitation_chance}% kans op neerslag</span>}
        {weather.wind_speed > 0 && <span>{Math.round(weather.wind_speed)} km/u wind</span>}
        {weather.mode === "manual" && <span>handmatig ingesteld</span>}
      </div>
      <div className="chips wrap" style={{ marginTop: 10 }}>
        {weather.tags.map((tag) => (
          <span className="tag" key={tag}>
            {WEATHER_ICONS[tag] ?? ""} {tag}
          </span>
        ))}
      </div>
      {advice && <p className="weather-advice">{advice}</p>}
    </div>
  );
}
