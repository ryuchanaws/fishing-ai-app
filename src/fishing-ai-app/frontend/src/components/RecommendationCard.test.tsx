import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RecommendationCard } from "./RecommendationCard";
import type { Recommendation } from "../types";

const baseRecommendation: Recommendation = {
  spotId: "spot-001",
  score: 85,
  fishTypes: ["アジ", "サバ"],
  reason: "潮の動きが良く、期待できます。",
  distance: 20,
  cost: 0,
  weatherScore: 90,
  tideScore: 80,
  spot: { spotId: "spot-001", name: "テストスポット", lat: 35.6, lng: 139.7 },
};

describe("RecommendationCard", () => {
  it("renders spot name, score, and fish tags", () => {
    render(
      <RecommendationCard
        recommendation={baseRecommendation}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );

    expect(screen.getByText("テストスポット")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("アジ")).toBeInTheDocument();
    expect(screen.getByText("サバ")).toBeInTheDocument();
  });

  it("shows a rank badge only when rank is provided", () => {
    const { rerender } = render(
      <RecommendationCard
        recommendation={baseRecommendation}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );
    expect(screen.queryByText("#1")).not.toBeInTheDocument();

    rerender(
      <RecommendationCard
        recommendation={baseRecommendation}
        rank={1}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("calls onClick with the recommendation when the card is clicked", () => {
    const handleClick = vi.fn();
    render(
      <RecommendationCard
        recommendation={baseRecommendation}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={handleClick}
      />
    );

    fireEvent.click(screen.getByText("テストスポット"));
    expect(handleClick).toHaveBeenCalledWith(baseRecommendation);
  });

  it("shows the hero photo only when rank is set and the spot has an image", () => {
    const withImage: Recommendation = {
      ...baseRecommendation,
      spot: { ...baseRecommendation.spot!, imageUrl: "https://example.com/photo.jpg" },
    };

    const { rerender } = render(
      <RecommendationCard
        recommendation={withImage}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );
    expect(screen.queryByRole("img", { name: "テストスポット" })).not.toBeInTheDocument();

    rerender(
      <RecommendationCard
        recommendation={withImage}
        rank={1}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );
    expect(screen.getByRole("img", { name: "テストスポット" })).toHaveAttribute(
      "src",
      "https://example.com/photo.jpg"
    );

    rerender(
      <RecommendationCard
        recommendation={baseRecommendation}
        rank={1}
        isFavorite={false}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    );
    expect(screen.queryByRole("img", { name: "テストスポット" })).not.toBeInTheDocument();
  });

  it("calls onToggleFavorite with the spotId when the favorite button is clicked", () => {
    const handleToggle = vi.fn();
    render(
      <RecommendationCard
        recommendation={baseRecommendation}
        isFavorite={false}
        onToggleFavorite={handleToggle}
        onClick={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText("保存"));
    expect(handleToggle).toHaveBeenCalledWith("spot-001");
  });
});
