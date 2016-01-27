from django.conf.urls import url

from send_money import views

app_name = 'send_money'
urlpatterns = [
    url(r'^$', views.SendMoneyView.as_view(), name='send_money'),
    url(r'^bank-transfer/$', views.bank_transfer_view, name='bank_transfer'),
    url(r'^card-payment/$', views.debit_card_view, name='debit_card'),
    url(r'^confirmation/$', views.confirmation_view, name='confirmation'),
]
