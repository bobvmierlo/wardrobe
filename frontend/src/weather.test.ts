/**
 * Which icon stands for a forecast.
 *
 * The tags come back in no particular order, and several can apply at once
 * ("Regen", "Koud", "Winderig"). Picking the wrong one is not cosmetic: a sun
 * above a rainy day is the app telling somebody the opposite of the truth.
 */

import { describe, expect, it } from "vitest";
import { weatherIcon } from "./components/WeatherCard";
import { WEATHER_ICONS } from "./types";

describe("weatherIcon", () => {
  it("lets the sky win over the temperature", () => {
    // "It is raining" says more about what to put on than "it is mild".
    expect(weatherIcon(["Koud", "Regen"])).toBe(WEATHER_ICONS.Regen);
    expect(weatherIcon(["Mild", "Bewolkt"])).toBe(WEATHER_ICONS.Bewolkt);
    expect(weatherIcon(["Heet", "Zonnig"])).toBe(WEATHER_ICONS.Zonnig);
  });

  it("puts snow above rain when both are named", () => {
    expect(weatherIcon(["Regen", "Sneeuw", "Koud"])).toBe(WEATHER_ICONS.Sneeuw);
  });

  it("falls back to the wind, then to the first tag, then to a thermometer", () => {
    expect(weatherIcon(["Winderig", "Mild"])).toBe(WEATHER_ICONS.Winderig);
    expect(weatherIcon(["Heet"])).toBe(WEATHER_ICONS.Heet);
    expect(weatherIcon([])).toBe("🌡️");
  });

  it("never hands back undefined for a tag it does not know", () => {
    expect(weatherIcon(["Zandstorm"])).toBe("🌡️");
  });
});
