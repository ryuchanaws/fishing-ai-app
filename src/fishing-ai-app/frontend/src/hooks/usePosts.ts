/**
 * 釣果投稿の状態管理カスタムフック。
 *
 * 投稿一覧の取得・新規投稿の作成・削除を提供する。
 * useFavorites.ts と同じ useState + useCallback + 楽観的更新のパターンを踏襲する。
 *
 * @module usePosts
 */
import { useState, useEffect, useCallback } from "react";
import type { Post } from "../types";
import { getPosts, createPost, deletePost as deletePostApi } from "../api/client";

/**
 * 釣果投稿を管理するカスタムフック。
 *
 * @returns {object} 投稿管理に必要な状態と操作関数
 * @returns {Post[]}    posts       - 投稿一覧（新しい順）
 * @returns {boolean}   loading     - データ取得中フラグ
 * @returns {string | null} error   - 一覧取得のエラーメッセージ
 * @returns {string | null} deleteError - 削除失敗時のエラーメッセージ
 * @returns {Function}  submitPost  - 新規投稿を作成する関数
 * @returns {Function}  removePost  - 投稿を削除する関数
 * @returns {Function}  refetch     - 投稿一覧を再取得する関数
 */
export const usePosts = () => {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  /**
   * 投稿一覧を取得してステートに反映する。
   */
  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPosts();
      setPosts(data);
    } catch {
      setError("投稿の取得に失敗しました");
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 新規投稿を作成し、成功したら一覧の先頭に楽観的に追加する。
   *
   * @param {object} input - 投稿内容（spotId・content必須、imageUrl・fishCaught省略可）
   * @returns {Promise<void>}
   */
  const submitPost = useCallback(
    async (input: { spotId: string; content: string; imageUrl?: string; fishCaught?: string[] }) => {
      const created = await createPost(input);
      setPosts((prev) => [created, ...prev]);
    },
    []
  );

  /**
   * 投稿を削除し、成功したら一覧からも取り除く。
   * 他人の投稿を削除しようとした場合など、backend側の所有者チェックで
   * 失敗する可能性があるため、エラーはdeleteErrorに反映してUIに表示する。
   *
   * @param {string} postId - 削除対象の投稿ID
   * @returns {Promise<void>}
   */
  const removePost = useCallback(async (postId: string) => {
    try {
      setDeleteError(null);
      await deletePostApi(postId);
      setPosts((prev) => prev.filter((p) => p.postId !== postId));
    } catch {
      setDeleteError("投稿の削除に失敗しました");
    }
  }, []);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  return { posts, loading, error, deleteError, submitPost, removePost, refetch: fetchPosts };
};
