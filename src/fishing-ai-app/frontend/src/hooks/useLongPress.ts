/**
 * 長押し検知用のカスタムフック。
 *
 * スマホでは hover が使えないため、画像プレビューの表示トリガーとして
 * 長押し（iOS の 3D Touch は廃止されたAPIのため代替できず、Web標準で
 * 実現できるロングプレスを採用）をPC側の hover と統一的に扱う。
 *
 * @module useLongPress
 */
import { useRef, useState, useCallback } from "react";

/** 長押しとみなす保持時間（ミリ秒） */
const LONG_PRESS_MS = 500;

/**
 * hover（PC）/ 長押し（スマホ）でプレビューの表示状態を管理するフック。
 *
 * @returns {object}
 * @returns {boolean} visible  - プレビューを表示すべきかどうか
 * @returns {object}  handlers - 対象要素にそのまま spread するイベントハンドラ群
 */
export const useLongPress = () => {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<number | null>(null);

  const show = useCallback(() => setVisible(true), []);
  const hide = useCallback(() => setVisible(false), []);

  const onTouchStart = useCallback(() => {
    timerRef.current = window.setTimeout(show, LONG_PRESS_MS);
  }, [show]);

  const cancelTouch = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    hide();
  }, [hide]);

  const handlers = {
    onMouseEnter: show,
    onMouseLeave: hide,
    onTouchStart,
    onTouchEnd: cancelTouch,
    onTouchMove: cancelTouch,
  };

  return { visible, handlers };
};
