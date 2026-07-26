/**
 * @fileoverview AIチャットの入力欄コンポーネント。
 *
 * テキスト入力に加えて、写真添付を「端末アルバムから選択」「その場で撮影」の
 * 2通りで行えるようにする（別々の機能に分けず、チャット入力の一部として統合）。
 */

import { useEffect, useRef, useState } from "react";
import { Send, Image as ImageIcon, Camera, X, LocateFixed, Loader2, Check } from "lucide-react";
import { useGeolocation } from "../hooks/useGeolocation";

/**
 * ChatInput コンポーネントの Props。
 */
interface ChatInputProps {
  /**
   * メッセージ送信時に呼び出す関数。
   * location は現在地共有トグルがONの場合のみ渡される（省略可、2026-07-26追加。
   * 「近くの釣り場は？」のような質問にAIが実データで答える精度を上げるために使う）
   */
  onSend: (text: string, file?: File, location?: { lat: number; lng: number }) => void;
  /** 送信中フラグ（true の間は入力・送信ボタンを無効化） */
  sending: boolean;
  /**
   * 編集中の元メッセージ本文（2026-07-26追加）。指定されると入力欄に反映され、
   * 編集モード（画像添付不可・送信ボタンが更新扱い）に切り替わる
   */
  editingText?: string;
  /** 編集モードを終了する関数（editingTextが指定されているときのみ使用） */
  onCancelEdit?: () => void;
}

/**
 * チャット入力欄コンポーネント。
 *
 * - 「アルバムから選択」ボタン: `<input type="file">`（capture属性なし）で端末の画像から選ぶ
 * - 「撮影する」ボタン: `<input type="file" capture="environment">` でその場でカメラを起動する
 *   （スマホのブラウザではcapture属性によりカメラアプリが直接開く）
 * - 選択した画像は送信前にサムネイルでプレビューし、送信前に取り消せる
 * - 現在地共有トグル（2026-07-26追加）: ONにすると以後の送信にlat/lngが付き、
 *   AIが「近くの釣り場」等の質問に実データ＋実距離で答えられるようになる（任意・オフが初期状態）
 *
 * @param {ChatInputProps} props
 * @returns {JSX.Element} チャット入力欄
 */
export const ChatInput = ({ onSend, sending, editingText, onCancelEdit }: ChatInputProps) => {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [locationEnabled, setLocationEnabled] = useState(false);
  const geo = useGeolocation();

  const galleryInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const isEditing = editingText !== undefined;

  /** 編集モードに入った/編集対象が変わったら、入力欄に元の本文を反映する */
  useEffect(() => {
    if (editingText !== undefined) {
      setText(editingText);
    }
  }, [editingText]);

  /** 現在地取得に初めて成功したら自動でトグルをONにする */
  useEffect(() => {
    if (geo.status === "granted") {
      setLocationEnabled(true);
    }
  }, [geo.status]);

  /**
   * 現在地共有トグルのクリック処理。
   * まだ位置情報を取得していなければリクエストし、取得済みならON/OFFを切り替える。
   */
  const handleToggleLocation = () => {
    if (geo.status === "granted") {
      setLocationEnabled((prev) => !prev);
    } else {
      geo.request();
    }
  };

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
   * メッセージを送信（または編集中の場合は訂正内容を確定）し、入力欄をリセットする。
   */
  const handleSend = () => {
    if (!text.trim() && !file) return;
    const location = locationEnabled && geo.position ? geo.position : undefined;
    onSend(text.trim(), file ?? undefined, location);
    setText("");
    clearImage();
  };

  return (
    <div className="chat-input-bar">
      {/* 編集モード表示: メッセージ訂正中であることを示し、キャンセルできるようにする（2026-07-26追加） */}
      {isEditing && (
        <div className="chat-editing-banner">
          <span>メッセージを編集中</span>
          <button
            className="chat-editing-cancel"
            onClick={() => {
              setText("");
              onCancelEdit?.();
            }}
            aria-label="編集をキャンセル"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {previewUrl && (
        <div className="chat-image-preview">
          <img src={previewUrl} alt="添付予定の画像" />
          <button className="chat-image-remove" onClick={clearImage} aria-label="画像を取り消す">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="chat-input-row">
        {/* アルバムから選択: capture属性なし。編集モードでは画像添付不可（本文のみ訂正対象） */}
        <button
          className="icon-btn"
          onClick={() => galleryInputRef.current?.click()}
          title="アルバムから選択"
          disabled={sending || isEditing}
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
          disabled={sending || isEditing}
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

        {/* 現在地共有トグル: ONの間は送信のたびに現在地をAIへの参考情報として付与する */}
        <button
          className="icon-btn"
          onClick={handleToggleLocation}
          title={locationEnabled ? "現在地を共有中（タップで解除）" : "現在地を共有して質問する"}
          aria-label="現在地の共有を切り替え"
          disabled={sending || isEditing || geo.status === "loading"}
          style={locationEnabled ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}
        >
          {geo.status === "loading" ? <Loader2 size={18} className="spin" /> : <LocateFixed size={18} />}
        </button>

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
          placeholder={isEditing ? "メッセージを編集..." : "このエサでいい？ 釣れた魚を判定して、など"}
          disabled={sending}
        />

        <button
          className="icon-btn chat-send-btn"
          onClick={handleSend}
          disabled={sending || (!text.trim() && !file)}
          aria-label={isEditing ? "更新" : "送信"}
          title={isEditing ? "更新" : "送信"}
        >
          {isEditing ? <Check size={18} /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
};
