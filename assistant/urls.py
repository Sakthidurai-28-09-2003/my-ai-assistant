from django.urls import path
from . import views
from django.contrib.auth import views as auth_views



urlpatterns = [
    path("", views.home, name="home"),

    path(
        "chat/<int:conversation_id>/",
        views.home,
        name="conversation"
    ),

    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.edit_profile_view, name="edit_profile"),
    path(
    "chat/<int:conversation_id>/delete/",
    views.delete_conversation,
    name="delete_conversation"
    ),
    path(
    "chat/<int:conversation_id>/rename/",
    views.rename_conversation,
    name="rename_conversation"
    ),
    path("settings/", views.settings_view, name="settings"),
    path(
    "password-reset/",
    views.password_reset_web,
    name="password_reset"
),

path(
    "password-reset/done/",
    auth_views.PasswordResetDoneView.as_view(
        template_name="assistant/password_reset_done.html"
    ),
    name="password_reset_done"
),

path(
    "reset/<uidb64>/<token>/",
    auth_views.PasswordResetConfirmView.as_view(
        template_name="assistant/password_reset_confirm.html"
    ),
    name="password_reset_confirm"
),

path(
    "reset/done/",
    auth_views.PasswordResetCompleteView.as_view(
        template_name="assistant/password_reset_complete.html"
    ),
    name="password_reset_complete"
),
path(
    "account/delete/",
    views.delete_account_view,
    name="delete_account"
),
path(
    "chat/<int:conversation_id>/regenerate/",
    views.regenerate_response,
    name="regenerate_response"
),
path(
    "transcribe/",
    views.transcribe_audio,
    name="transcribe_audio"
),
path(
    "chat/<int:conversation_id>/export/",
    views.export_conversation,
    name="export_conversation"
),

path(
    "api/test/",
    views.api_test,
    name="api_test"
),

path(
    "api/register/",
    views.api_register,
    name="api_register"
),
path(
    "api/login/",
    views.api_login,
    name="api_login"
),

path(
    "api/conversations/",
    views.api_conversations,
    name="api_conversations"
),

path(
    "api/conversations/create/",
    views.api_create_conversation,
    name="api_create_conversation"
),

path(
    "api/conversations/<int:conversation_id>/message/",
    views.api_send_message,
    name="api_send_message"
),

path(
    "api/conversations/<int:conversation_id>/",
    views.api_conversation_messages,
    name="api_conversation_messages"
),

path(
    "api/conversations/<int:conversation_id>/delete/",
    views.api_delete_conversation,
    name="api_delete_conversation"
),

path(
    "api/password-reset/",
    views.api_password_reset,
    name="api_password_reset"
),

path(
    "api/profile/",
    views.api_profile,
    name="api_profile"
),
    
]