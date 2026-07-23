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
   * ポーリング間隔（ミリ秒）と最大試行回数。
   * Gemini API呼び出しを含むバッチ処理は5スポットで30秒前後かかるため、
   * 3秒間隔 × 20回 = 最大60秒間ポーリングする。
   */
  const POLL_INTERVAL_MS = 3000;
  const MAX_POLL_ATTEMPTS = 20;

  /**
   * AI バッチを非同期起動し、完了をポーリングで検知する。
   * 「AI分析を実行」ボタンから呼び出される。
   *
   * バッチ起動(POST /admin/run-ai-batch)はAPI Gatewayの29秒タイムアウトを
   * 避けるため非同期化されており、起動直後にレスポンスが返る。そのため
   * ここでは起動後に GET /recommendations を定期的に呼び出し、全件の
   * updatedAt が起動時刻より新しくなった時点で完了とみなす。
   * 一定時間内に完了を確認できない場合は "timeout" として扱う
   * （失敗ではなく、裏側では処理が続いている可能性がある）。
   */
  const triggerAiBatch = useCallback(async () => {
    const startedAt = new Date().toISOString();
    setBatchStatus({ status: "running", startedAt });
    try {
      await runAiBatch();
    } catch {
      setBatchStatus({ status: "failed", message: "AI分析の起動に失敗しました" });
      return;
    }

    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

      try {
        const data = await getRecommendations();
        const allUpdated =
          data.length > 0 &&
          data.every((rec) => (rec.updatedAt ?? "") > startedAt);

        if (allUpdated) {
          const sorted = [...data].sort((a, b) => b.score - a.score);
          setRecommendations(sorted);
          setBatchStatus({ status: "completed", startedAt, completedAt: new Date().toISOString() });
          return;
        }
      } catch {
        // ポーリング中の一時的なエラーは無視して次の試行を続ける
      }
    }

    // 規定回数ポーリングしても完了を確認できなかった場合
    setBatchStatus({
      status: "timeout",
      startedAt,
      message: "バックグラウンドで実行中の可能性があります。しばらくしてから更新してください",
    });
  }, []);

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