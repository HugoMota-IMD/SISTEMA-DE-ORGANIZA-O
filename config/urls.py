from django.urls import path
from finance import views

urlpatterns = [
    path('', views.index),
    path('static/<path:asset>', views.static_asset),
    path('api/session', views.session_info),
    path('api/health', views.health),
    path('api/auth/register', views.register),
    path('api/auth/login', views.sign_in),
    path('api/auth/logout', views.sign_out),
    path('api/technical/users', views.technical_users),
    path('api/technical/users/<int:user_id>/status', views.technical_user_status),
    path('api/spaces', views.spaces),
    path('api/spaces/<uuid:space_id>/state', views.state),
    path('api/spaces/<uuid:space_id>/actions', views.actions),
    path('api/spaces/<uuid:space_id>/members', views.members),
    path('api/spaces/<uuid:space_id>/members/<int:member_id>', views.member_update),
]
