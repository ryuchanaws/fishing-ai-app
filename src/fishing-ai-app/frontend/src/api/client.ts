/**
 * @fileoverview API Gateway へのHTTPリクエストを担当するAPIクライアント。
 * axios インスタンスを共有し、全エンドポイントへのアクセスを提供する。
 */

import axios from "axios";
import type { Recommendation, Spot, Post, Favorite, BatchStatus, UploadPresignResponse } from "../types";

/**
 * API Gateway のベースURL。
 * 環境変数 VITE_API_BASE_URL が未設定の場合はプレースホルダーを使用する。
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "https://your-api-id.execute-api.ap-northeast-1.amazonaws.com/prod";

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
 * @param {string} userId - ユーザーID
 * @param {string} spotId - 追加するスポットID
 * @param {string} [memo] - メモ（省略可）
 * @returns {Promise<void>}
 */
export const addFavorite = async (userId: string, spotId: string, memo?: string): Promise<void> => {
  await api.post("/favorites", { userId, spotId, memo });
};

/**
 * お気に入りスポットを削除する。
 *
 * @param {string} userId - ユーザーID
 * @param {string} spotId - 削除するスポットID
 * @returns {Promise<void>}
 */
export const removeFavorite = async (userId: string, spotId: string): Promise<void> => {
  await api.delete(`/favorites/${spotId}?userId=${userId}`);
};

/**
 * AI バッチ処理を非同期に起動する。
 *
 * POST /admin/run-ai-batch を呼び出し、generateSpotScoreBatch Lambda を
 * 非同期起動する。バッチの完了は待たず、起動を受け付けた時点で即座に返る
 * （API Gateway の29秒タイムアウトを回避するため）。
 * 完了確認は呼び出し側で GET /recommendations をポーリングして行う。
 *
 * @returns {Promise<BatchStatus>} 起動受付結果（status: "started", startedAt を含む）
 */
export const runAiBatch = async (): Promise<BatchStatus> => {
  const { data } = await api.post("/admin/run-ai-batch");
  return data;
};

/**
 * 新規釣りスポット候補の自動探索バッチを非同期に起動する。
 *
 * POST /admin/run-spot-discovery を呼び出し、Google Places API を使った
 * 新規スポット探索バッチを起動する。runAiBatch 同様、完了は待たずに
 * 起動を受け付けた時点で即座に返る。
 *
 * @returns {Promise<BatchStatus>} 起動受付結果（status: "started", startedAt を含む）
 */
export const runSpotDiscovery = async (): Promise<BatchStatus> => {
  const { data } = await api.post("/admin/run-spot-discovery");
  return data;
};

/**
 * 釣果投稿を作成する。
 *
 * @param {object} input
 * @param {string} input.spotId - 投稿対象のスポットID
 * @param {string} input.content - 投稿本文
 * @param {string} [input.imageUrl] - 添付画像のURL（uploadImageToS3完了後のpublicUrlを渡す）
 * @param {string[]} [input.fishCaught] - 釣れた魚種リスト
 * @returns {Promise<Post>} 作成された投稿
 */
export const createPost = async (input: {
  spotId: string;
  content: string;
  imageUrl?: string;
  fishCaught?: string[];
}): Promise<Post> => {
  const { data } = await api.post("/posts", input);
  return data.post;
};

/**
 * スポットの写真URLを設定する。
 *
 * @param {string} spotId - 対象スポットID
 * @param {string} imageUrl - 設定する画像URL（uploadImageToS3完了後のpublicUrl）
 * @returns {Promise<void>}
 */
export const updateSpotImage = async (spotId: string, imageUrl: string): Promise<void> => {
  await api.put(`/spots/${spotId}/image`, { imageUrl });
};

/**
 * S3への直接アップロード用の署名付きURLを発行する。
 *
 * @param {string} contentType - アップロードする画像のMIMEタイプ（例: "image/jpeg"）
 * @returns {Promise<UploadPresignResponse>} 署名付きアップロードURLと公開URL
 */
export const getPresignedUploadUrl = async (contentType: string): Promise<UploadPresignResponse> => {
  const { data } = await api.post("/uploads/presign", { contentType });
  return data;
};

/**
 * 発行された署名付きURLへ画像ファイルを直接アップロードする。
 *
 * API Gatewayのペイロードサイズ制限を避けるため、Lambdaを経由せず
 * S3へ直接PUTする（共有axiosインスタンスは使わない。別ホストのため）。
 *
 * @param {string} uploadUrl - getPresignedUploadUrl で取得した署名付きPUT URL
 * @param {File} file - アップロードする画像ファイル
 * @returns {Promise<void>}
 */
export const uploadImageToS3 = async (uploadUrl: string, file: File): Promise<void> => {
  const res = await fetch(uploadUrl, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type },
  });
  if (!res.ok) {
    throw new Error(`Image upload failed: ${res.status}`);
  }
};