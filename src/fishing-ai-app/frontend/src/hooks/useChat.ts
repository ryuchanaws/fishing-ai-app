/**
 * AIチャットの状態管理カスタムフック。
 *
 * 現在の会話（messages/chatId）・送信中フラグ・履歴一覧の取得と、
 * メッセージ送信（画像添付含む）・新しい会話の開始・履歴からの再開を提供する。
 * useFavorites.ts / usePosts.ts と同じ useState + useCallback パターンを踏襲する。
 *
 * @module useChat
 */
import { useState, useCallback } from "react";
import axios from "axios";
import type { ChatMessage, ChatSummary } from "../types";
import {
  sendChatMessage,
  getChatHistory,
  getChat,
  deleteChat as deleteChatApi,
  getPresignedUploadUrl,
  uploadImageToS3,
} from "../api/client";

/**
 * AIチャットを管理するカスタムフック。
 *
 * @returns {object} チャット管理に必要な状態と操作関数
 * @returns {ChatMessage[]} messages       - 現在の会話のメッセージ一覧
 * @returns {string | null} chatId         - 現在の会話ID（新規会話でまだ送信していない場合は null）
 * @returns {boolean}       sending        - メッセージ送信中フラグ
 * @returns {string | null} error          - エラーメッセージ
 * @returns {ChatSummary[]} history        - チャット履歴一覧
 * @returns {boolean}       historyLoading - 履歴取得中フラグ
 * @returns {Function}      send           - メッセージ送信関数（テキスト + 任意で画像ファイル）
 * @returns {Function}      startNewChat   - 現在の会話をリセットして新しい会話を開始する
 * @returns {Function}      loadHistory    - チャット履歴一覧を取得する
 * @returns {Function}      openChat       - 履歴から特定の会話を開いて再開する
 */
export const useChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ChatSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  /**
   * メッセージを送信する。画像ファイルが指定されている場合は
   * 先にS3へアップロードしてからそのpublicUrlを添付して送信する。
   *
   * @param {string} text - 送信するメッセージ本文
   * @param {File} [file] - 添付する画像ファイル（任意）
   * @returns {Promise<void>}
   */
  const send = useCallback(
    async (text: string, file?: File) => {
      setSending(true);
      setError(null);

      let imageUrl: string | undefined;
      try {
        if (file) {
          const { uploadUrl, uploadFields, publicUrl } = await getPresignedUploadUrl(file.type);
          await uploadImageToS3(uploadUrl, uploadFields, file);
          imageUrl = publicUrl;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "画像のアップロードに失敗しました");
        setSending(false);
        return;
      }

      const now = new Date().toISOString();
      // 送信直後にユーザー発言を楽観的に表示する
      setMessages((prev) => [...prev, { role: "user", content: text, imageUrl, createdAt: now }]);

      try {
        const result = await sendChatMessage({ chatId: chatId ?? undefined, message: text, imageUrl });
        setChatId(result.chatId);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: result.reply, createdAt: result.updatedAt },
        ]);
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 429) {
          // Geminiコスト管理のための1日あたり利用上限（backend: DAILY_CHAT_LIMIT）に達した場合
          setError(err.response.data?.message ?? "本日の利用上限に達しました。明日またお試しください。");
        } else {
          setError("AIからの応答取得に失敗しました");
        }
      } finally {
        setSending(false);
      }
    },
    [chatId]
  );

  /**
   * 現在の会話をリセットして新しい会話を開始する。
   * DBには何も書き込まない（次の send() 呼び出し時に新規チャットとして作成される）。
   */
  const startNewChat = useCallback(() => {
    setMessages([]);
    setChatId(null);
    setError(null);
  }, []);

  /**
   * チャット履歴一覧を取得する。
   */
  const loadHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);
      const data = await getChatHistory();
      setHistory(data);
    } catch {
      setError("履歴の取得に失敗しました");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  /**
   * 履歴から特定の会話を開いて現在の会話として復元する。
   *
   * @param {string} id - 開くチャットID
   * @returns {Promise<void>}
   */
  const openChat = useCallback(async (id: string) => {
    try {
      const chat = await getChat(id);
      setChatId(chat.chatId);
      setMessages(chat.messages);
      setError(null);
    } catch {
      setError("会話の読み込みに失敗しました");
    }
  }, []);

  /**
   * チャットを削除し、履歴一覧からも取り除く。
   * 削除したチャットが現在開いている会話だった場合は、表示中の会話もリセットする。
   *
   * @param {string} id - 削除対象のチャットID
   * @returns {Promise<void>}
   */
  const removeChat = useCallback(
    async (id: string) => {
      await deleteChatApi(id);
      setHistory((prev) => prev.filter((h) => h.chatId !== id));
      if (chatId === id) {
        setMessages([]);
        setChatId(null);
      }
    },
    [chatId]
  );

  return {
    messages,
    chatId,
    sending,
    error,
    history,
    historyLoading,
    send,
    startNewChat,
    loadHistory,
    openChat,
    removeChat,
  };
};
