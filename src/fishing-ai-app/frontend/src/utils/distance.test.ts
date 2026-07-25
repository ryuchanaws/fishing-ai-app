import { describe, it, expect } from "vitest";
import { haversineKm } from "./distance";

describe("haversineKm", () => {
  it("returns 0 for the same point", () => {
    expect(haversineKm(35.681, 139.767, 35.681, 139.767)).toBe(0);
  });

  it("returns roughly 27km between Tokyo Station and Yokohama Station", () => {
    const d = haversineKm(35.681, 139.767, 35.466, 139.622);
    expect(d).toBeGreaterThan(24);
    expect(d).toBeLessThan(30);
  });
});
