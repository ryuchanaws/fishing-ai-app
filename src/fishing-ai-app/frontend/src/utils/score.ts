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