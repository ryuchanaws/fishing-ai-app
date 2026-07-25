import { describe, it, expect } from "vitest";
import { getScoreColor, getScoreLabel, formatScore, recalcScoreForDistance } from "./score";

describe("getScoreColor", () => {
  it("returns green for high scores (>= 80)", () => {
    expect(getScoreColor(85)).toBe("#00c896");
    expect(getScoreColor(80)).toBe("#00c896");
  });

  it("returns orange for mid scores (60-79)", () => {
    expect(getScoreColor(65)).toBe("#f5a623");
  });

  it("returns red for low scores (< 60)", () => {
    expect(getScoreColor(30)).toBe("#e05c5c");
  });
});

describe("getScoreLabel", () => {
  it("labels scores across all thresholds", () => {
    expect(getScoreLabel(85)).toBe("絶好調");
    expect(getScoreLabel(65)).toBe("良好");
    expect(getScoreLabel(45)).toBe("普通");
    expect(getScoreLabel(20)).toBe("低め");
  });
});

describe("formatScore", () => {
  it("rounds to the nearest integer string", () => {
    expect(formatScore(85.4)).toBe("85");
    expect(formatScore(62.7)).toBe("63");
  });
});

describe("recalcScoreForDistance", () => {
  it("returns the same score when distance does not change", () => {
    const rec = { score: 70, distance: 20 };
    expect(recalcScoreForDistance(rec, 20)).toBeCloseTo(70);
  });

  it("increases score when the new distance is closer than the original", () => {
    const rec = { score: 70, distance: 50 };
    const result = recalcScoreForDistance(rec, 10);
    expect(result).toBeGreaterThan(70);
  });

  it("decreases score when the new distance is farther than the original", () => {
    const rec = { score: 70, distance: 10 };
    const result = recalcScoreForDistance(rec, 90);
    expect(result).toBeLessThan(70);
  });

  it("clamps the result to the 0-100 range", () => {
    const rec = { score: 99, distance: 0 };
    const result = recalcScoreForDistance(rec, 1000);
    expect(result).toBeGreaterThanOrEqual(0);
    expect(result).toBeLessThanOrEqual(100);
  });
});
