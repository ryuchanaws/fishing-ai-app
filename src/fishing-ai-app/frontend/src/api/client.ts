/**
 * client.ts
 *
 * API Gateway へのHTTPリクエストを担当するAPIクライアント。
 * axios インスタンスを共有し、全エンドポイントへのアクセスを提供する。
 *
 * @module client
 */

import axios from "axios";
import type { Recommendation, Spot, Post, Favorite, BatchStatus } from "../types";

/**
 * API Gateway のベースURL。
 * 環境変数 VITE_API_BASE_URL が未設定の場合はプレースホルダーを使用する。
 */
const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://your-api-id.execute-api.ap-northeast-1.amazonaws.com/prod";

/**
 * 共有 axios インスタンス。
 * タイムアウト・Content-Type ヘッダーをデフォルト設定済み。
 */
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

/**
 * おすすめスポット一覧を取得する。
 *
 * @returns {Promise<Recommendation[]>} スコア降順のおすすめスポットリスト
 */
export const getRecommendations = async (): Promise<Recommendation[]> => {
  const { data } = await api.get("/recommendations");
  return data.items ?? data;
};

/**
 * 全釣りスポット一覧を取得する。
 *
 * @returns {Promise<Spot[]>} 全スポットリスト
 */
export const getSpots = async (): Promise<Spot[]> => {
  const { data } = await api.get("/spots");
  return data.items ?? data;
};

/**
 * 投稿一覧を取得する。
 *
 * @returns {Promise<Post[]>} 新しい順にソートされた投稿リスト
 */
export const getPosts = async (): Promise<Post[]> => {
  const { data } = await api.get("/posts");
  return data.items ?? data;
};

/**
 * 指定ユーザーのお気に入りスポット一覧を取得する。
 *
 * @param {string} userId - ユーザーID
 * @returns {Promise<Favorite[]>} お気に入りスポットリスト
 */
export const getFavorites = async (userId: string): Promise<Favorite[]> => {
  const { data } = await api.get(`/favorites?userId=${userId}`);
  return data.items ?? data;
};

/**
 * お気に入りスポットを追加する。
 *
 * @param {string} userId  - ユーザーID
 * @param {string} spotId  - 追加するスポットID
 * @param {string} [memo]  - メモ（省略可）
 * @returns {Promise<void>}
 */
export const addFavorite = async (
  userId: string,
  spotId: string,
  memo?: string
): Promise<void> => {
  await api.post("/favorites", { userId, spotId, memo });
};

/**
 * お気に入りスポットを削除する。
 *
 * @param {string} userId - ユーザーID
 * @param {string} spotId - 削除するスポットID
 * @returns {Promise<void>}
 */
export const removeFavorite = async (
  userId: string,
  spotId: string
): Promise<void> => {
  await api.delete(`/favorites/${spotId}?userId=${userId}`);
};

/**
 * AI バッチ処理を手動実行する。
 *
 * POST /admin/run-ai-batch を呼び出し、
 * generateSpotScoreBatch Lambda を起動してスコアと推薦理由を更新する。
 *
 * @returns {Promise<BatchStatus>} バッチ処理の実行結果
 */
export const runAiBatch = async (): Promise<BatchStatus> => {
  const { data } = await api.post("/admin/run-ai-batch");
  return data;
};