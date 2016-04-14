from django.conf import settings
from django.conf.urls import url

from send_money import views

app_name = 'send_money'

if settings.SHOW_DEBIT_CARD_OPTION:
    urlpatterns = [
        url(r'^$', views.SendMoneyView.as_view(), name='send_money'),
        url(r'^check-details/$', views.CheckDetailsView.as_view(), name='check_details'),
        url(r'^clear-session/$', views.clear_session_view, name='clear_session'),
        url(r'^card-payment/$', views.debit_card_view, name='debit_card'),
        url(r'^confirmation/$', views.confirmation_view, name='confirmation'),
    ]
elif settings.SHOW_BANK_TRANSFER_OPTION:
    urlpatterns = [
        url(r'^$', views.SendMoneyBankTransferView.as_view(), name='send_money'),
    ]

if settings.SHOW_BANK_TRANSFER_OPTION:
    urlpatterns += [
        url(r'^bank-transfer/$', views.bank_transfer_view, name='bank_transfer'),
    ]
