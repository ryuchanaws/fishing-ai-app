/**
 * @fileoverview チャット履歴一覧モーダルコンポーネント。
 *
 * 過去の会話一覧を表示し、選択した会話を再開できるようにする。
 * DetailModal/NearbyModal と同じ .modal-backdrop/.modal-panel パターンを流用する。
 */

import { X, MessageSquareText, Trash2 } from "lucide-react";
import type { ChatSummary } from "../types";

/**
 * ChatHistoryPanel コンポーネントの Props。
 */
interface ChatHistoryPanelProps {
  /** チャット履歴一覧（新しい順） */
  history: ChatSummary[];
  /** 履歴取得中フラグ */
  loading: boolean;
  /** 履歴項目クリック時に呼び出す関数（該当チャットを開く） */
  onSelect: (chatId: string) => void;
  /** 削除ボタンクリック時に呼び出す関数（該当チャットを削除する） */
  onDelete: (chatId: string) => void;
  /** モーダルを閉じる関数 */
  onClose: () => void;
}

/**
 * チャット履歴一覧モーダル。
 *
 * @param {ChatHistoryPanelProps} props
 * @returns {JSX.Element} チャット履歴モーダル
 */
export const ChatHistoryPanel = ({ history, loading, onSelect, onDelete, onClose }: ChatHistoryPanelProps) => {
  /**
   * 確認ダイアログを挟んでチャットを削除する。
   * 親要素（履歴項目）のクリック（会話を開く）へ伝播しないよう stopPropagation する。
   *
   * @param {React.MouseEvent} e - クリックイベント
   * @param {string} chatId - 削除対象のチャットID
   */
  const handleDelete = (e: React.MouseEvent, chatId: string) => {
    e.stopPropagation();
    if (window.confirm("この会話を削除しますか？")) {
      onDelete(chatId);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="閉じる">
          <X size={20} />
        </button>

        <div className="modal-hero">
          <h2 className="modal-spot-name">会話履歴</h2>
        </div>

        <div className="modal-section">
          {loading ? (
            <div className="loading-state">
              <div className="loader" />
              <p>読み込み中...</p>
            </div>
          ) : history.length === 0 ? (
            <p className="reason-text">まだ会話履歴がありません</p>
          ) : (
            <div className="chat-history-list">
              {history.map((h) => (
                <div
                  key={h.chatId}
                  className="chat-history-item"
                  onClick={() => onSelect(h.chatId)}
                  role="button"
                  tabIndex={0}
                >
                  <MessageSquareText size={16} />
                  <span className="chat-history-title">{h.title || "無題の会話"}</span>
                  <span className="chat-history-date">{new Date(h.updatedAt).toLocaleString("ja-JP")}</span>
                  <button
                    className="icon-btn"
                    onClick={(e) => handleDelete(e, h.chatId)}
                    title="削除"
                    aria-label="会話を削除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
