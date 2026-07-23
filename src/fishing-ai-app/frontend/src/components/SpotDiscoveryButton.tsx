/**
 * @fileoverview 新規スポット自動発見バッチを手動実行するボタンコンポーネント。
 *
 * AiBatchButton と違い、発見結果はすぐには反映されないため
 * 完了ポーリングは行わず、起動受付のみを案内する単純な作りにしている。
 */

import { useState } from "react";
import { Compass, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { runSpotDiscovery } from "../api/client";

/** ボタンの実行状態 */
type Status = "idle" | "running" | "done" | "error";

/**
 * 新規スポット発見バッチ実行ボタンコンポーネント。
 *
 * クリックで POST /admin/run-spot-discovery を起動し、
 * 起動を受け付けた時点で完了扱いとする（バッチ自体の完了は待たない）。
 *
 * @returns {JSX.Element} 新規スポット発見ボタンと結果メッセージ
 */
export const SpotDiscoveryButton = () => {
  const [status, setStatus] = useState<Status>("idle");

  /**
   * バッチ起動をリクエストする。
   */
  const handleRun = async () => {
    setStatus("running");
    try {
      await runSpotDiscovery();
      setStatus("done");
    } catch {
      setStatus("error");
    }
  };

  const isRunning = status === "running";

  return (
    <div className="ai-batch-wrapper">
      <button
        className={`ai-batch-btn ${isRunning ? "running" : ""}`}
        onClick={handleRun}
        disabled={isRunning}
        aria-label="新しい釣りスポットを探す"
      >
        {isRunning ? (
          <>
            <Loader2 size={18} className="spin" />
            <span>探索中...</span>
          </>
        ) : (
          <>
            <Compass size={18} />
            <span>新スポットを探す</span>
          </>
        )}
      </button>

      {status === "done" && (
        <div className="batch-status success">
          <CheckCircle2 size={14} />
          <span>探索を開始しました。数分後に更新ボタンを押してください</span>
        </div>
      )}

      {status === "error" && (
        <div className="batch-status error">
          <AlertCircle size={14} />
          <span>探索の起動に失敗しました</span>
        </div>
      )}
    </div>
  );
};
