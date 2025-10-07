from django.shortcuts import render
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.db.models import Q, Count, F
from django.shortcuts import get_object_or_404
from .models import Post, Tag, Comment, Like, Bookmark, CommentLike
from .serializers import (
    PostListSerializer, PostDetailSerializer, PostCreateUpdateSerializer,
    TagSerializer, CommentSerializer, LikeSerializer, BookmarkSerializer
)
from .permissions import IsAuthorOrReadOnly

class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'content', 'tags__name']
    ordering_fields = ['created_at', 'views_count', 'likes_count', 'published_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = Post.objects.select_related('author', 'author__profile').prefetch_related('tags', 'comments')
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        elif self.action == 'list':
            # By default, only show published posts for list view
            if not self.request.user.is_authenticated:
                queryset = queryset.filter(status='published')
            else:
                # Show all posts for authenticated users, but prioritize published
                queryset = queryset.filter(Q(status='published') | Q(author=self.request.user))
        
        # Filter by author
        author_id = self.request.query_params.get('author', None)
        if author_id:
            queryset = queryset.filter(author_id=author_id)
        
        # Filter by tag
        tag_slug = self.request.query_params.get('tag', None)
        if tag_slug:
            queryset = queryset.filter(tags__slug=tag_slug)
        
        # Filter by search query
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(content__icontains=search) |
                Q(tags__name__icontains=search)
            ).distinct()
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PostDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PostCreateUpdateSerializer
        return PostListSerializer
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count
        instance.views_count = F('views_count') + 1
        instance.save(update_fields=['views_count'])
        instance.refresh_from_db()
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_posts(self, request):
        """Get all posts by the current user"""
        queryset = self.get_queryset().filter(author=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        """Like or unlike a post"""
        post = self.get_object()
        like, created = Like.objects.get_or_create(post=post, user=request.user)
        
        if not created:
            # Unlike
            like.delete()
            post.likes_count = max(0, post.likes_count - 1)
            post.save(update_fields=['likes_count'])
            return Response({'status': 'unliked', 'likes_count': post.likes_count})
        else:
            # Like
            post.likes_count = F('likes_count') + 1
            post.save(update_fields=['likes_count'])
            post.refresh_from_db()
            return Response({'status': 'liked', 'likes_count': post.likes_count})
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bookmark(self, request, pk=None):
        """Bookmark or unbookmark a post"""
        post = self.get_object()
        bookmark, created = Bookmark.objects.get_or_create(post=post, user=request.user)
        
        if not created:
            # Remove bookmark
            bookmark.delete()
            return Response({'status': 'unbookmarked'})
        else:
            # Add bookmark
            return Response({'status': 'bookmarked'})
    
    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAuthenticatedOrReadOnly])
    def comments(self, request, pk=None):
        """Get or create comments for a post"""
        post = self.get_object()
        
        if request.method == 'GET':
            comments = Comment.objects.filter(post=post, parent=None).select_related('author')
            serializer = CommentSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data)
        
        elif request.method == 'POST':
            serializer = CommentSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save(author=request.user, post=post)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get trending posts based on views and likes"""
        queryset = self.get_queryset().filter(status='published').annotate(
            engagement=F('views_count') + F('likes_count') * 2
        ).order_by('-engagement')[:10]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.annotate(posts_count=Count('posts')).order_by('-posts_count')
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    
    @action(detail=True, methods=['get'])
    def posts(self, request, pk=None):
        """Get all posts for a specific tag"""
        tag = self.get_object()
        posts = Post.objects.filter(tags=tag, status='published')
        serializer = PostListSerializer(posts, many=True, context={'request': request})
        return Response(serializer.data)

class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.select_related('author', 'post').all()
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    def update(self, request, *args, **kwargs):
        """Update comment - only author can edit"""
        comment = self.get_object()
        
        # Check if user is the author
        if comment.author != request.user:
            return Response(
                {'error': 'You can only edit your own comments'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Only allow content to be updated
        content = request.data.get('content', '').strip()
        if not content:
            return Response(
                {'error': 'Comment content cannot be empty'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comment.content = content
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update comment - only author can edit"""
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete comment - only author can delete"""
        comment = self.get_object()
        
        # Check if user is the author
        if comment.author != request.user:
            return Response(
                {'error': 'You can only delete your own comments'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Delete the comment (this will also delete replies due to CASCADE)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def reply(self, request, pk=None):
        print("trigger.............................")
        """Reply to a comment"""
        parent_comment = self.get_object()
        print("parent_comment", parent_comment)
        serializer = CommentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            print("parent_comment", parent_comment)
            serializer.save(
                author=request.user,
                post=parent_comment.post,
                parent=parent_comment
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        """Like or unlike a comment"""
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(comment=comment, user=request.user)
        
        if not created:
            # Unlike
            like.delete()
            comment.likes_count = max(0, comment.likes_count - 1)
            comment.save(update_fields=['likes_count'])
            return Response({
                'status': 'unliked',
                'likes_count': comment.likes_count
            })
        else:
            # Like
            comment.likes_count = F('likes_count') + 1
            comment.save(update_fields=['likes_count'])
            comment.refresh_from_db()
            return Response({
                'status': 'liked',
                'likes_count': comment.likes_count
            })

class BookmarkViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BookmarkSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user).select_related('post', 'post__author')
