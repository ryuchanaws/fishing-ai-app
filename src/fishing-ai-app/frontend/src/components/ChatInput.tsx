/**
 * @fileoverview AIチャットの入力欄コンポーネント。
 *
 * テキスト入力に加えて、写真添付を「端末アルバムから選択」「その場で撮影」の
 * 2通りで行えるようにする（別々の機能に分けず、チャット入力の一部として統合）。
 */

import { useRef, useState } from "react";
import { Send, Image as ImageIcon, Camera, X } from "lucide-react";

/**
 * ChatInput コンポーネントの Props。
 */
interface ChatInputProps {
  /** メッセージ送信時に呼び出す関数（テキスト + 任意で画像ファイル） */
  onSend: (text: string, file?: File) => void;
  /** 送信中フラグ（true の間は入力・送信ボタンを無効化） */
  sending: boolean;
}

/**
 * チャット入力欄コンポーネント。
 *
 * - 「アルバムから選択」ボタン: `<input type="file">`（capture属性なし）で端末の画像から選ぶ
 * - 「撮影する」ボタン: `<input type="file" capture="environment">` でその場でカメラを起動する
 *   （スマホのブラウザではcapture属性によりカメラアプリが直接開く）
 * - 選択した画像は送信前にサムネイルでプレビューし、送信前に取り消せる
 *
 * @param {ChatInputProps} props
 * @returns {JSX.Element} チャット入力欄
 */
export const ChatInput = ({ onSend, sending }: ChatInputProps) => {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const galleryInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  /**
   * ファイル選択時にプレビュー用のオブジェクトURLを生成する。
   *
   * @param {File | undefined} selected - 選択されたファイル
   */
  const handleFileSelect = (selected: File | undefined) => {
    if (!selected) return;
    setFile(selected);
    setPreviewUrl(URL.createObjectURL(selected));
  };

  /**
   * 選択中の画像プレビューを取り消す。
   */
  const clearImage = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
  };

  /**
   * メッセージを送信し、入力欄をリセットする。
   */
  const handleSend = () => {
    if (!text.trim() && !file) return;
    onSend(text.trim(), file ?? undefined);
    setText("");
    clearImage();
  };

  return (
    <div className="chat-input-bar">
      {previewUrl && (
        <div className="chat-image-preview">
          <img src={previewUrl} alt="添付予定の画像" />
          <button className="chat-image-remove" onClick={clearImage} aria-label="画像を取り消す">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="chat-input-row">
        {/* アルバムから選択: capture属性なし */}
        <button
          className="icon-btn"
          onClick={() => galleryInputRef.current?.click()}
          title="アルバムから選択"
          disabled={sending}
        >
          <ImageIcon size={18} />
        </button>
        <input
          ref={galleryInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          style={{ display: "none" }}
          onChange={(e) => handleFileSelect(e.target.files?.[0])}
        />

        {/* その場で撮影: capture="environment" でカメラを直接起動 */}
        <button
          className="icon-btn"
          onClick={() => cameraInputRef.current?.click()}
          title="撮影する"
          disabled={sending}
        >
          <Camera size={18} />
        </button>
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          style={{ display: "none" }}
          onChange={(e) => handleFileSelect(e.target.files?.[0])}
        />

        <input
          className="chat-text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="このエサでいい？ 釣れた魚を判定して、など"
          disabled={sending}
        />

        <button
          className="icon-btn chat-send-btn"
          onClick={handleSend}
          disabled={sending || (!text.trim() && !file)}
          aria-label="送信"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
};
