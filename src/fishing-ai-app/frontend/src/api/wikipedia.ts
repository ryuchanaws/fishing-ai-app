/**
 * @fileoverview 魚種の参考画像をWikipediaから取得するユーティリティ。
 *
 * スポット写真のようにアップロード管理する必要がない「図鑑的な画像」
 * （魚種・エサ）のために、都度Wikipedia日本語版のサムネイルを取得する。
 * アップロード・保存インフラを持たないための軽量な代替手段。
 */

/** 取得結果をメモリ内でキャッシュし、同じ魚種への再取得を避ける */
const thumbnailCache = new Map<string, string | null>();

/**
 * Wikipedia日本語版から指定した名称のページサムネイル画像URLを取得する。
 *
 * ページが存在しない・サムネイルが無い場合は null を返す
 * （呼び出し側でプレースホルダー表示にフォールバックする）。
 * セッション内では同じ名称を再取得しないようキャッシュする。
 *
 * @param {string} name - 検索する名称（例: "アジ"）
 * @returns {Promise<string | null>} サムネイル画像のURL、取得できない場合は null
 */
export const getWikipediaThumbnail = async (name: string): Promise<string | null> => {
  if (thumbnailCache.has(name)) {
    return thumbnailCache.get(name) ?? null;
  }

  try {
    const res = await fetch(`https://ja.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(name)}`);
    if (!res.ok) {
      thumbnailCache.set(name, null);
      return null;
    }
    const data = await res.json();
    const url: string | null = data?.thumbnail?.source ?? null;
    thumbnailCache.set(name, url);
    return url;
  } catch {
    // ネットワークエラー等は静かに失敗させ、呼び出し側のフォールバック表示に任せる
    thumbnailCache.set(name, null);
    return null;
  }
};
