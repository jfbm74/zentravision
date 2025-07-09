from django.urls import path
from django.contrib.auth import views as auth_views
from django.shortcuts import render

def home(request):
    return render(request, 'home.html' if 'home.html' else 'admin/base.html', {
        'title': 'Zentravision',
        'message': 'Aplicación funcionando correctamente!'
    })

urlpatterns = [
    path('', home, name='home'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', home, name='dashboard'),
]
