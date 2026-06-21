/**
 * @fileoverview おすすめスポットの状態管理カスタムフック。
 *
 * おすすめデータの取得・AI バッチの手動実行・実行状態の管理を提供する。
 */

import { useState, useEffect, useCallback } from "react";
import type { Recommendation, BatchStatus } from "../types";
import { getRecommendations, runAiBatch } from "../api/client";

/**
 * おすすめスポットを管理するカスタムフック。
 *
 * @returns {object} おすすめ管理に必要な状態と操作関数
 * @returns {Recommendation[]} recommendations - スコア降順のおすすめリスト
 * @returns {boolean}          loading         - データ取得中フラグ
 * @returns {BatchStatus}      batchStatus     - AI バッチの実行状態
 * @returns {string | null}    error           - エラーメッセージ
 * @returns {Function}         triggerAiBatch  - AI バッチを手動実行する関数
 * @returns {Function}         refetch         - おすすめデータを再取得する関数
 */
export const useRecommendations = () => {
  /** スコア降順にソートされたおすすめスポット一覧 */
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  /** データ取得中フラグ */
  const [loading, setLoading] = useState(true);

  /** AI バッチの実行状態 */
  const [batchStatus, setBatchStatus] = useState<BatchStatus>({ status: "idle" });

  /** エラーメッセージ（エラーなしの場合は null） */
  const [error, setError] = useState<string | null>(null);

  /**
   * おすすめデータを API から取得してスコア降順にソートする。
   */
  const fetchRecommendations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getRecommendations();
      const sorted = [...data].sort((a, b) => b.score - a.score);
      setRecommendations(sorted);
    } catch {
      setError("おすすめ情報の取得に失敗しました");
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * AI バッチを手動実行し、完了後におすすめデータを再取得する。
   * 「AI分析を実行」ボタンから呼び出される。
   */
  const triggerAiBatch = useCallback(async () => {
    setBatchStatus({ status: "running", startedAt: new Date().toISOString() });
    try {
      const result = await runAiBatch();
      setBatchStatus({ ...result, status: "completed" });
      await fetchRecommendations();
    } catch {
      setBatchStatus({ status: "failed", message: "AI分析の実行に失敗しました" });
    }
  }, [fetchRecommendations]);

  /** マウント時におすすめデータを初回取得する */
  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  return {
    recommendations,
    loading,
    batchStatus,
    error,
    triggerAiBatch,
    refetch: fetchRecommendations,
  };
};