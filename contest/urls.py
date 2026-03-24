from django.urls import path
from . import views

urlpatterns = [
    # Home & Auth
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Quiz Flow
    path('start-quiz/<int:round_number>/', views.start_quiz, name='start_quiz'),
    path('quiz/<int:round_number>/', views.quiz, name='quiz'),
    path('submit-answer/', views.submit_answer, name='submit_answer'),
    path('submit-quiz/<int:round_number>/', views.submit_quiz, name='submit_quiz'),
    path('quiz-result/<int:round_number>/', views.quiz_result, name='quiz_result'),
    path(
        'quiz-answer-sheet/<int:round_number>/',
        views.quiz_answer_sheet,
        name='quiz_answer_sheet',
    ),
    
    # Leaderboard
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('leaderboard-api/', views.leaderboard_api, name='leaderboard_api'),
    
    # REMOVE OR COMMENT OUT THIS LINE:
    # path('admin/analytics/', views.admin_analytics, name='admin_analytics'),
]