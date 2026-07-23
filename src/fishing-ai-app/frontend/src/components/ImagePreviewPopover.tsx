/**
 * @fileoverview 画像プレビューのポップオーバー表示コンポーネント。
 *
 * hover（PC）/ 長押し（スマホ）で子要素の下に画像プレビューを表示する。
 * imageUrl が渡された場合はそれを直接表示し（スポット写真）、
 * 渡されなかった場合は fishName から Wikipedia のサムネイルを都度取得する
 * （魚種・エサの参考画像）。どちらも取得できない場合は🎣プレースホルダーを表示する。
 */

import { useEffect, useState, type ReactNode } from "react";
import { ImageOff } from "lucide-react";
import { useLongPress } from "../hooks/useLongPress";
import { getWikipediaThumbnail } from "../api/wikipedia";

/**
 * ImagePreviewPopover コンポーネントの Props。
 */
interface ImagePreviewPopoverProps {
  /** プレビュー対象となるトリガー要素（スポット名・魚種タグなど） */
  children: ReactNode;
  /** スポット写真など、直接表示する画像URL（省略時は fishName から解決を試みる） */
  imageUrl?: string;
  /** Wikipediaサムネイル検索に使う名称（例: 魚種名） */
  fishName?: string;
  /** ラッパー要素に付与する追加クラス名（省略可） */
  className?: string;
}

/**
 * hover/長押しで画像プレビューを表示するラッパーコンポーネント。
 *
 * @param {ImagePreviewPopoverProps} props
 * @returns {JSX.Element} トリガー要素 + 条件付きの画像プレビュー
 */
export const ImagePreviewPopover = ({ children, imageUrl, fishName, className }: ImagePreviewPopoverProps) => {
  const { visible, handlers } = useLongPress();
  const [wikiUrl, setWikiUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  /** 表示された時点で imageUrl が無ければ Wikipedia サムネイルを遅延取得する */
  useEffect(() => {
    if (!visible || imageUrl || !fishName || wikiUrl !== null) return;
    setLoading(true);
    getWikipediaThumbnail(fishName).then((url) => {
      setWikiUrl(url);
      setLoading(false);
    });
  }, [visible, imageUrl, fishName, wikiUrl]);

  const resolvedUrl = imageUrl ?? wikiUrl;

  return (
    <span className={`image-preview-wrapper ${className ?? ""}`} {...handlers}>
      {children}
      {visible && (
        <div className="image-preview-popover">
          {loading ? (
            <span className="image-preview-placeholder">🎣</span>
          ) : resolvedUrl ? (
            <img src={resolvedUrl} alt={fishName ?? "プレビュー"} loading="lazy" />
          ) : (
            <span className="image-preview-placeholder">
              <ImageOff size={20} />
            </span>
          )}
        </div>
      )}
    </span>
  );
};
