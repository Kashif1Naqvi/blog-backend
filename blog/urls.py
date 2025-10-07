from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PostViewSet, TagViewSet, CommentViewSet, BookmarkViewSet

router = DefaultRouter()
router.register(r'posts', PostViewSet, basename='post')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'bookmarks', BookmarkViewSet, basename='bookmark')

urlpatterns = [
    path('', include(router.urls)),
]



# This creates these URL patterns:
# 
# POSTS:
# GET    /api/blog/posts/                  - List all posts
# POST   /api/blog/posts/                  - Create a post
# GET    /api/blog/posts/{id}/             - Get post detail
# PUT    /api/blog/posts/{id}/             - Update post
# DELETE /api/blog/posts/{id}/             - Delete post
# GET    /api/blog/posts/my-posts/         - Get my posts (custom action)
# GET    /api/blog/posts/trending/         - Get trending posts (custom action)
# POST   /api/blog/posts/{id}/like/        - Like/unlike post
# POST   /api/blog/posts/{id}/bookmark/    - Bookmark/unbookmark post
#
# COMMENTS:
# GET    /api/blog/comments/               - List all comments (filtered by post)
# POST   /api/blog/comments/               - Create a comment
# GET    /api/blog/comments/{id}/          - Get comment detail
# PUT    /api/blog/comments/{id}/          - Update comment
# DELETE /api/blog/comments/{id}/          - Delete comment
# POST   /api/blog/comments/{id}/reply/    - Reply to a comment
#
# TAGS:
# GET    /api/blog/tags/                   - List all tags
# GET    /api/blog/tags/{id}/              - Get tag detail
# GET    /api/blog/tags/{id}/posts/        - Get posts for a tag
#
# BOOKMARKS:
# GET    /api/blog/bookmarks/              - List user's bookmarks