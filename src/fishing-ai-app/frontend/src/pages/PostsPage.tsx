/**
 * @fileoverview 釣果投稿一覧ページ。
 *
 * 投稿を新しい順に一覧表示し、「投稿する」ボタンから新規投稿を作成できる。
 * URLクエリパラメータ ?spotId=X が付いている場合は該当スポットの投稿のみに絞り込む
 * （DetailModalの「このスポットの投稿を見る」リンクからの遷移用）。
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { Fish, Plus, Trash2 } from "lucide-react";
import { usePosts } from "../hooks/usePosts";
import { PostForm } from "../components/PostForm";
import { getSpots } from "../api/client";
import type { Spot } from "../types";

/**
 * 釣果投稿一覧ページコンポーネント。
 *
 * @returns {JSX.Element} 投稿一覧画面
 */
export const PostsPage = () => {
  const auth = useAuth();
  const { posts, loading, error, deleteError, submitPost, removePost } = usePosts();
  const [spots, setSpots] = useState<Spot[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [searchParams] = useSearchParams();
  const spotIdFilter = searchParams.get("spotId");

  /** 投稿フォームのスポット選択肢・スポット名表示用に一覧を取得する */
  useEffect(() => {
    getSpots().then(setSpots);
  }, []);

  const spotName = (spotId: string) => spots.find((s) => s.spotId === spotId)?.name ?? spotId;

  const visiblePosts = spotIdFilter ? posts.filter((p) => p.spotId === spotIdFilter) : posts;

  /**
   * 確認ダイアログを挟んで投稿を削除する。
   *
   * @param {string} postId - 削除対象の投稿ID
   */
  const handleDelete = (postId: string) => {
    if (window.confirm("この投稿を削除しますか？")) {
      removePost(postId);
    }
  };

  /**
   * 「投稿する」ボタンのクリック処理。
   * /posts (POST) はCognito認証必須のため、未ログイン時はフォームを開かずログイン画面へ誘導する。
   */
  const handleOpenForm = () => {
    if (!auth.isAuthenticated) {
      auth.signinRedirect();
      return;
    }
    setShowForm(true);
  };

  return (
    <div className="page posts-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">釣果投稿</h1>
          <p className="page-sub">
            {spotIdFilter ? `${spotName(spotIdFilter)}の投稿` : "みんなの釣果をチェック"}
          </p>
        </div>
        <button className="icon-btn" onClick={handleOpenForm} title="投稿する">
          <Plus size={18} />
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {deleteError && <div className="error-banner">{deleteError}</div>}

      {loading ? (
        <div className="loading-state">
          <div className="loader" />
          <p>読み込み中...</p>
        </div>
      ) : visiblePosts.length === 0 ? (
        <div className="empty-state">
          <p>まだ投稿がありません</p>
          <p className="empty-hint">「投稿する」ボタンから釣果をシェアしましょう</p>
        </div>
      ) : (
        <div className="posts-list">
          {visiblePosts.map((post) => (
            <div key={post.postId} className="post-card">
              {post.imageUrl && <img className="post-image" src={post.imageUrl} alt={post.content} loading="lazy" />}
              <div className="post-body">
                <div className="post-header-row">
                  <p className="post-spot-name">{spotName(post.spotId)}</p>
                  {/* 自分の投稿にのみ削除ボタンを表示する（他人の投稿はbackend側でも403になるが、UI上も出さない） */}
                  {auth.user?.profile.sub === post.userId && (
                    <button className="icon-btn" onClick={() => handleDelete(post.postId)} title="削除" aria-label="投稿を削除">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
                <p className="post-content">{post.content}</p>
                {post.fishCaught && post.fishCaught.length > 0 && (
                  <div className="fish-tags">
                    {post.fishCaught.map((f) => (
                      <span key={f} className="fish-tag sm">
                        <Fish size={10} />
                        {f}
                      </span>
                    ))}
                  </div>
                )}
                <p className="post-date">
                  {post.authorName ?? "匿名"} ・ {new Date(post.createdAt).toLocaleString("ja-JP")}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <PostForm
          spots={spots}
          defaultSpotId={spotIdFilter ?? undefined}
          onSubmit={submitPost}
          onClose={() => setShowForm(false)}
        />
      )}
    </div>
  );
};
