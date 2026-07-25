/**
 * @fileoverview AIチャットページ。
 *
 * 釣りに関する質問（魚種判定・エサの適否・釣果へのコメント等）を、
 * 写真添付（アルバムから選択 or その場で撮影）込みでAIに相談できる画面。
 * 会話はDBに保存され、「履歴」から過去の会話を再開できる。
 * 「新しい会話」を開始した場合は空の状態から始まる。
 */

import { useEffect, useRef, useState } from "react";
import { Plus, History, Loader2 } from "lucide-react";
import { useChat } from "../hooks/useChat";
import { ChatInput } from "../components/ChatInput";
import { ChatHistoryPanel } from "../components/ChatHistoryPanel";

/**
 * AIチャットページコンポーネント。
 *
 * - メッセージ送信のたびに自動で最下部までスクロールする
 * - 「新しい会話」ボタンで現在の会話をリセットする（DBには何も書き込まない）
 * - 「履歴」ボタンで過去の会話一覧を開き、選択した会話を再開する
 *
 * @returns {JSX.Element} AIチャット画面
 */
export const ChatPage = () => {
  const { messages, sending, error, history, historyLoading, send, startNewChat, loadHistory, openChat } =
    useChat();
  const [showHistory, setShowHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  /** メッセージが増えるたびに最下部までスクロール */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  /**
   * 履歴パネルを開き、履歴一覧を取得する。
   */
  const handleOpenHistory = () => {
    setShowHistory(true);
    loadHistory();
  };

  /**
   * 履歴から会話を選択し、パネルを閉じる。
   *
   * @param {string} chatId - 開くチャットID
   */
  const handleSelectHistory = async (chatId: string) => {
    await openChat(chatId);
    setShowHistory(false);
  };

  return (
    <div className="page chat-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">AI相談</h1>
          <p className="page-sub">写真も添えて、魚種やエサについて質問できます</p>
        </div>
        <div className="page-header-actions">
          <button className="icon-btn" onClick={startNewChat} title="新しい会話">
            <Plus size={18} />
          </button>
          <button className="icon-btn" onClick={handleOpenHistory} title="履歴">
            <History size={18} />
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <p>まだメッセージがありません</p>
            <p className="empty-hint">「このエサでアジは釣れる？」のように質問してみましょう</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role}`}>
            {m.imageUrl && <img className="chat-bubble-image" src={m.imageUrl} alt="添付画像" />}
            <p className="chat-bubble-text">{m.content}</p>
          </div>
        ))}

        {sending && (
          <div className="chat-bubble assistant chat-bubble-loading">
            <Loader2 size={16} className="spin" />
            <span>考え中...</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={send} sending={sending} />

      {showHistory && (
        <ChatHistoryPanel
          history={history}
          loading={historyLoading}
          onSelect={handleSelectHistory}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
};
