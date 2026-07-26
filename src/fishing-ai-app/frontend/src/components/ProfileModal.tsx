/**
 * @fileoverview 表示名（ユーザー名）の設定・編集モーダル。
 *
 * ログイン後にまだ表示名を設定していない場合はNavBarから自動表示され、
 * 「閉じる」で後回しにもできる。設定済みの表示名の編集にも同じモーダルを使う。
 */

import { useState } from "react";
import { X } from "lucide-react";

/**
 * ProfileModal コンポーネントの Props。
 */
interface ProfileModalProps {
  /** 現在の表示名（未設定の場合は null / undefined） */
  currentName?: string | null;
  /** 保存時に呼び出す関数 */
  onSave: (name: string) => Promise<void>;
  /** モーダルを閉じる関数（保存せず後回しにする場合も呼ばれる） */
  onClose: () => void;
}

/**
 * 表示名設定モーダル。
 *
 * - PostForm.tsx と同じ `.modal-backdrop`/`.modal-panel` パターンを使う
 * - 保存成功時に自動で閉じる
 *
 * @param {ProfileModalProps} props
 * @returns {JSX.Element} 表示名設定フォーム（モーダル）
 */
export const ProfileModal = ({ currentName, onSave, onClose }: ProfileModalProps) => {
  const [name, setName] = useState(currentName ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("表示名を入力してください");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await onSave(name.trim());
      onClose();
    } catch {
      setError("保存に失敗しました。もう一度お試しください");
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
          <h2 className="modal-spot-name">{currentName ? "表示名を編集" : "表示名を設定しましょう"}</h2>
        </div>

        <form className="modal-section post-form" onSubmit={handleSubmit}>
          {!currentName && (
            <p className="page-sub">投稿などで、あなたの名前として使われます。あとから変更もできます。</p>
          )}

          <label className="post-form-label">
            表示名
            <input
              className="post-form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={30}
              placeholder="例: りゅうちゃん"
              autoFocus
            />
          </label>

          {error && <div className="error-banner">{error}</div>}

          <button className="btn-nav" type="submit" disabled={submitting}>
            {submitting ? "保存中..." : "保存する"}
          </button>
        </form>
      </div>
    </div>
  );
};
