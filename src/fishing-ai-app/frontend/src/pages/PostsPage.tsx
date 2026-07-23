/**
 * @fileoverview 釣果投稿一覧ページ。
 *
 * 投稿を新しい順に一覧表示し、「投稿する」ボタンから新規投稿を作成できる。
 * URLクエリパラメータ ?spotId=X が付いている場合は該当スポットの投稿のみに絞り込む
 * （DetailModalの「このスポットの投稿を見る」リンクからの遷移用）。
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Fish, Plus } from "lucide-react";
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
  const { posts, loading, error, submitPost } = usePosts();
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

  return (
    <div className="page posts-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">釣果投稿</h1>
          <p className="page-sub">
            {spotIdFilter ? `${spotName(spotIdFilter)}の投稿` : "みんなの釣果をチェック"}
          </p>
        </div>
        <button className="icon-btn" onClick={() => setShowForm(true)} title="投稿する">
          <Plus size={18} />
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

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
                <p className="post-spot-name">{spotName(post.spotId)}</p>
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
                <p className="post-date">{new Date(post.createdAt).toLocaleString("ja-JP")}</p>
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
