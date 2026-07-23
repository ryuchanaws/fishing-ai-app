/**
 * @fileoverview 現在地周辺の新規スポット探索バッチを手動実行するボタンコンポーネント。
 *
 * 全国向けの探索は「AI分析を実行」のたびに自動で行われるため、
 * このボタンはユーザーの現在地に絞った探索専用。
 * 現在地取得 → discoverSpotsBatch起動 の2段階になるため、
 * AiBatchButton と違い先に位置情報の許可が必要になる。
 * 発見結果はすぐには反映されないため、AiBatchButtonのような
 * 完了ポーリングは行わず、起動受付のみを案内する。
 */

import { useState } from "react";
import { LocateFixed, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { runSpotDiscovery } from "../api/client";

/** ボタンの実行状態 */
type Status = "idle" | "locating" | "running" | "done" | "error" | "denied";

/**
 * 現在地から新規スポットを探索するボタンコンポーネント。
 *
 * クリックで現在地を取得し、取得できたら
 * POST /admin/run-spot-discovery を { lat, lng } 付きで起動する。
 * 起動を受け付けた時点で完了扱いとする（バッチ自体の完了は待たない）。
 *
 * @returns {JSX.Element} 現在地から探すボタンと結果メッセージ
 */
export const SpotDiscoveryButton = () => {
  const [status, setStatus] = useState<Status>("idle");

  /**
   * 現在地を取得し、取得できたらバッチ起動をリクエストする。
   */
  const handleRun = () => {
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setStatus("running");
        try {
          await runSpotDiscovery({ lat: pos.coords.latitude, lng: pos.coords.longitude });
          setStatus("done");
        } catch {
          setStatus("error");
        }
      },
      (err) => {
        setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  };

  const isBusy = status === "locating" || status === "running";

  return (
    <div className="ai-batch-wrapper">
      <button
        className={`ai-batch-btn ${isBusy ? "running" : ""}`}
        onClick={handleRun}
        disabled={isBusy}
        aria-label="現在地から新しい釣りスポットを探す"
      >
        {isBusy ? (
          <>
            <Loader2 size={18} className="spin" />
            <span>{status === "locating" ? "現在地を取得中..." : "探索中..."}</span>
          </>
        ) : (
          <>
            <LocateFixed size={18} />
            <span>現在地から新スポットを探す</span>
          </>
        )}
      </button>

      {status === "done" && (
        <div className="batch-status success">
          <CheckCircle2 size={14} />
          <span>探索を開始しました。数分後にスポット一覧を確認してください</span>
        </div>
      )}

      {status === "denied" && (
        <div className="batch-status error">
          <AlertCircle size={14} />
          <span>位置情報の利用が許可されていません</span>
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
