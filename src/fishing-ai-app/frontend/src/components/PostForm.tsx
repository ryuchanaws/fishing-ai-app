/**
 * @fileoverview 釣果投稿フォームコンポーネント。
 *
 * スポット選択・本文・釣れた魚種・写真（任意）を入力し、
 * 写真がある場合はS3へアップロードしてから投稿を作成する。
 */

import { useState } from "react";
import { X, Camera } from "lucide-react";
import type { Spot } from "../types";
import { getPresignedUploadUrl, uploadImageToS3 } from "../api/client";

/**
 * PostForm コンポーネントの Props。
 */
interface PostFormProps {
  /** スポット選択肢一覧 */
  spots: Spot[];
  /** 初期選択するスポットID（省略可。クエリパラメータからの絞り込み時などに使用） */
  defaultSpotId?: string;
  /** 投稿作成時に呼び出す関数 */
  onSubmit: (input: { spotId: string; content: string; imageUrl?: string; fishCaught?: string[] }) => Promise<void>;
  /** フォームを閉じる関数 */
  onClose: () => void;
}

/**
 * 釣果投稿フォームコンポーネント。
 *
 * - 写真が選択されている場合、送信時に署名付きURLでS3へアップロードしてから
 *   その publicUrl を imageUrl として投稿を作成する
 * - fishCaught はカンマ区切りテキストを配列に変換して送信する
 *
 * @param {PostFormProps} props
 * @returns {JSX.Element} 投稿作成フォーム（モーダル）
 */
export const PostForm = ({ spots, defaultSpotId, onSubmit, onClose }: PostFormProps) => {
  const [spotId, setSpotId] = useState(defaultSpotId ?? spots[0]?.spotId ?? "");
  const [content, setContent] = useState("");
  const [fishCaughtText, setFishCaughtText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * フォーム送信処理。写真があればアップロードを先に済ませてから投稿する。
   *
   * @param {React.FormEvent} e - フォーム送信イベント
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!spotId || !content.trim()) {
      setError("スポットと本文は必須です");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      let imageUrl: string | undefined;
      if (file) {
        const { uploadUrl, publicUrl } = await getPresignedUploadUrl(file.type);
        await uploadImageToS3(uploadUrl, file);
        imageUrl = publicUrl;
      }

      const fishCaught = fishCaughtText
        .split(",")
        .map((f) => f.trim())
        .filter(Boolean);

      await onSubmit({ spotId, content: content.trim(), imageUrl, fishCaught });
      onClose();
    } catch {
      setError("投稿に失敗しました。もう一度お試しください");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="閉じる">
          <X size={20} />
        </button>

        <div className="modal-hero">
          <h2 className="modal-spot-name">釣果を投稿</h2>
        </div>

        <form className="modal-section post-form" onSubmit={handleSubmit}>
          <label className="post-form-label">
            スポット
            <select className="post-form-select" value={spotId} onChange={(e) => setSpotId(e.target.value)}>
              {spots.map((s) => (
                <option key={s.spotId} value={s.spotId}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>

          <label className="post-form-label">
            本文
            <textarea
              className="post-form-textarea"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="釣れた魚や状況を書いてみましょう"
              rows={4}
            />
          </label>

          <label className="post-form-label">
            釣れた魚種（カンマ区切り、任意）
            <input
              className="post-form-input"
              value={fishCaughtText}
              onChange={(e) => setFishCaughtText(e.target.value)}
              placeholder="例: アジ, サバ"
            />
          </label>

          <label className="post-form-label post-form-file">
            <Camera size={16} />
            {file ? file.name : "写真を選択（任意）"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              style={{ display: "none" }}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          {error && <div className="error-banner">{error}</div>}

          <button className="btn-nav" type="submit" disabled={submitting}>
            {submitting ? "投稿中..." : "投稿する"}
          </button>
        </form>
      </div>
    </div>
  );
};
