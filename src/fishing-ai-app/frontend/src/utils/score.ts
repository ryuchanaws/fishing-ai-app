/**
 * @fileoverview スコア表示に関するユーティリティ関数群。
 *
 * スポットの総合スコア（0〜100）を元に
 * 色・ラベル・アイコンへの変換を担当する。
 * RecommendationCard・DetailModal・SpotsPage などで共通利用する。
 */

/**
 * スコアに応じた色コードを返す。
 * 地図マーカー・スコアサークル・スコアバーの色分けに使用する。
 *
 * @param {number} score - 総合スコア（0〜100）
 * @returns {string} カラーコード（16進数）
 *
 * @example
 * getScoreColor(85); // "#00c896"（緑）
 * getScoreColor(65); // "#f5a623"（オレンジ）
 * getScoreColor(30); // "#e05c5c"（赤）
 */
export const getScoreColor = (score: number): string => {
  if (score >= 80) return "#00c896"; // 高スコア: 緑
  if (score >= 60) return "#f5a623"; // 中スコア: オレンジ
  return "#e05c5c";                  // 低スコア: 赤
};

/**
 * スコアに応じた日本語ラベルを返す。
 * スコアサークル・スポット一覧の補足テキストに使用する。
 *
 * @param {number} score - 総合スコア（0〜100）
 * @returns {string} スコアラベル（日本語）
 *
 * @example
 * getScoreLabel(85); // "絶好調"
 * getScoreLabel(65); // "良好"
 * getScoreLabel(45); // "普通"
 * getScoreLabel(20); // "低め"
 */
export const getScoreLabel = (score: number): string => {
  if (score >= 80) return "絶好調";
  if (score >= 60) return "良好";
  if (score >= 40) return "普通";
  return "低め";
};

/**
 * スコアを整数に丸めた文字列を返す。
 * スコアサークル内の数値表示に使用する。
 *
 * @param {number} score - 総合スコア（0〜100）
 * @returns {string} 整数に丸めたスコアの文字列
 *
 * @example
 * formatScore(85.4); // "85"
 * formatScore(62.7); // "63"
 */
export const formatScore = (score: number): string => Math.round(score).toString();

/**
 * 天気スコアに応じた天気絵文字アイコンを返す。
 * カード・詳細画面の天気情報表示に使用する。
 *
 * @param {number} score - 天気スコア（0〜100）
 * @returns {string} 天気を表す絵文字
 *
 * @example
 * getWeatherIcon(85); // "☀️"（晴れ）
 * getWeatherIcon(65); // "⛅"（くもり時々晴れ）
 * getWeatherIcon(45); // "🌥️"（くもり）
 * getWeatherIcon(20); // "🌧️"（雨）
 */
export const getWeatherIcon = (score: number): string => {
  if (score >= 80) return "☀️";  // 晴れ
  if (score >= 60) return "⛅";  // くもり時々晴れ
  if (score >= 40) return "🌥️"; // くもり
  return "🌧️";                  // 雨
};

/**
 * 潮汐スコアに応じた潮汐絵文字アイコンを返す。
 * カード・詳細画面の潮汐情報表示に使用する。
 *
 * @param {number} score - 潮汐スコア（0〜100）
 * @returns {string} 潮汐状態を表す絵文字
 *
 * @example
 * getTideIcon(85); // "🌊"（大潮・好条件）
 * getTideIcon(65); // "〰️"（中潮・普通）
 * getTideIcon(30); // "💧"（小潮・低条件）
 */
export const getTideIcon = (score: number): string => {
  if (score >= 80) return "🌊"; // 大潮・好条件
  if (score >= 60) return "〰️"; // 中潮・普通
  return "💧";                  // 小潮・低条件
};

/**
 * 距離（km）をバックエンドの calc_score と同じ正規化係数(0〜100)に変換する。
 * distanceKm/100 を 0〜100 にクランプして返す（backend/lambda/batch/generate_score.py
 * の calc_score() 内の dist_norm と同一の計算式）。
 *
 * @param {number} km - 距離（km）
 * @returns {number} 正規化された距離（0〜100）
 */
const normalizeDistance = (km: number): number => Math.min(km / 100, 1) * 100;

/**
 * 実際の現在地からの距離を使ってスコアを近似的に再計算する。
 *
 * バックエンドの calc_score() は score に「距離ペナルティ(-distNorm*0.1)」を
 * 織り込み済みで保存しているため、そのままでは距離だけを差し替えられない。
 * ここでは元の distanceKm 由来のペナルティを一度打ち消し、
 * 実際の現在地からの距離で計算し直したペナルティを掛け直すことで、
 * DBを書き換えずにクライアント側だけで「現在地基準の順位」を近似する。
 *
 * @param {Recommendation} rec - 元のおすすめデータ（score・distance を含む）
 * @param {number} newDistanceKm - 現在地からの実距離（km）
 * @returns {number} 現在地基準に再計算したスコア（0〜100）
 */
export const recalcScoreForDistance = (
  rec: { score: number; distance: number },
  newDistanceKm: number
): number => {
  const delta = (normalizeDistance(rec.distance) - normalizeDistance(newDistanceKm)) * 0.1;
  return Math.max(0, Math.min(100, rec.score + delta));
};