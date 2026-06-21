/**
 * お気に入りスポットの状態管理カスタムフック。
 *
 * お気に入りの取得・追加・削除・存在確認を提供する。
 * 個人利用を想定しユーザーIDは USER_ID に固定している。
 *
 * @module useFavorites
 */
import { useState, useEffect, useCallback } from "react";
import type { Favorite } from "../types";
import { getFavorites, addFavorite, removeFavorite } from "../api/client";

/** 固定ユーザーID（個人利用想定のため定数化） */
const USER_ID = "user-001";

/**
 * お気に入りスポットを管理するカスタムフック。
 *
 * @returns {object} お気に入り管理に必要な状態と操作関数
 * @returns {Favorite[]} favorites     - お気に入りスポットの一覧
 * @returns {boolean}   loading        - データ取得中フラグ
 * @returns {Function}  toggleFavorite - お気に入りの追加・削除トグル
 * @returns {Function}  isFavorite     - 指定スポットのお気に入り登録有無を返す関数
 * @returns {Function}  refetch        - お気に入り一覧を再取得する関数
 *
 * @example
 * const { favorites, loading, toggleFavorite, isFavorite } = useFavorites();
 *
 * // お気に入りのトグル
 * await toggleFavorite("spot-001", "メモ");
 *
 * // お気に入り確認
 * const saved = isFavorite("spot-001"); // true | false
 */
export const useFavorites = () => {
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [loading, setLoading] = useState(true);

  /**
   * DynamoDB からお気に入り一覧を取得してステートに反映する。
   *
   * useCallback でメモ化しており、依存配列が空なので
   * コンポーネントのマウント時に一度だけ生成される。
   *
   * @returns {Promise<void>}
   */
  const fetchFavorites = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getFavorites(USER_ID);
      setFavorites(data);
    } catch {
      console.error("Failed to load favorites");
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 指定スポットのお気に入り状態をトグルする。
   *
   * - 既にお気に入り登録済みの場合 → API で削除しステートからも除去
   * - 未登録の場合 → API で追加しステートにも追記
   *
   * @param {string} spotId - トグル対象のスポットID
   * @param {string} [memo] - お気に入り登録時のメモ（追加時のみ有効）
   * @returns {Promise<void>}
   */
  const toggleFavorite = useCallback(async (spotId: string, memo?: string) => {
    const exists = favorites.some((f) => f.spotId === spotId);
    if (exists) {
      await removeFavorite(USER_ID, spotId);
      setFavorites((prev) => prev.filter((f) => f.spotId !== spotId));
    } else {
      await addFavorite(USER_ID, spotId, memo);
      setFavorites((prev) => [...prev, { userId: USER_ID, spotId, memo }]);
    }
  }, [favorites]);

  /**
   * 指定スポットがお気に入り登録済みかどうかを返す。
   *
   * favorites ステートが変わるたびに再生成される。
   *
   * @param {string} spotId - 確認対象のスポットID
   * @returns {boolean} お気に入り登録済みなら true
   */
  const isFavorite = useCallback(
    (spotId: string) => favorites.some((f) => f.spotId === spotId),
    [favorites]
  );

  /**
   * マウント時にお気に入り一覧を初回取得する。
   * fetchFavorites が再生成された場合も再実行される。
   */
  useEffect(() => {
    fetchFavorites();
  }, [fetchFavorites]);

  return { favorites, loading, toggleFavorite, isFavorite, refetch: fetchFavorites };
};