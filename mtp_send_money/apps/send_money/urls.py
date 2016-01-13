from django.conf.urls import url

from send_money import views

urlpatterns = [
    url(r'^$', views.SendMoneyView.as_view(), name='send_money'),
]
