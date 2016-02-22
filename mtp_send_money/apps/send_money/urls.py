from django.conf.urls import url
from django.views.generic import TemplateView

from send_money import views

app_name = 'send_money'
urlpatterns = [
    url(r'^$', views.SendMoneyView.as_view(), name='send_money'),
    url(r'^check-details/$', views.CheckDetailsView.as_view(), name='check_details'),
    url(r'^clear-session/$', views.clear_session_view, name='clear_session'),
    url(r'^bank-transfer/$', views.bank_transfer_view, name='bank_transfer'),
    url(r'^card-payment/$', views.debit_card_view, name='debit_card'),
    url(r'^confirmation/$', views.confirmation_view, name='confirmation'),

    url(
        r'^privacy-policy/$',
        TemplateView.as_view(template_name='send_money/privacy-policy.html'),
        name='privacy_policy',
    ),
    url(
        r'^cookies/$',
        TemplateView.as_view(template_name='send_money/cookies.html'),
        name='cookies',
    ),
]
