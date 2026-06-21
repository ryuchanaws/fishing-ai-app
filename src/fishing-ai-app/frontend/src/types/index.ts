export interface Spot {
  spotId: string;
  name: string;
  lat: number;
  lng: number;
  prefecture?: string;
  description?: string;
}

export interface Recommendation {
  spotId: string;
  score: number;
  fishTypes: string[];
  reason: string;
  distance: number;
  cost: number;
  weatherScore: number;
  tideScore: number;
  updatedAt?: string;
  spot?: Spot;
}

export interface Favorite {
  userId: string;
  spotId: string;
  memo?: string;
  spot?: Spot;
  recommendation?: Recommendation;
}

export interface Post {
  postId: string;
  spotId: string;
  userId: string;
  content: string;
  imageUrl?: string;
  fishCaught?: string[];
  createdAt: string;
  spot?: Spot;
}

export interface BatchStatus {
  status: "running" | "completed" | "failed" | "idle";
  startedAt?: string;
  completedAt?: string;
  message?: string;
  processedCount?: number;
}