from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_file, name='upload_file'),
    path('status/<int:file_id>/', views.file_status, name='file_status'),
    path('download/<int:file_id>/', views.download_file, name='download_file'),
]