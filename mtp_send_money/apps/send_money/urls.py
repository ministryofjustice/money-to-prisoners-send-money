from django.conf import settings
from django.conf.urls import url

from send_money import views

app_name = 'send_money'

if settings.SHOW_DEBIT_CARD_OPTION and settings.SHOW_BANK_TRANSFER_OPTION:
    urlpatterns = [
        url(r'^$', views.ChooseMethodView.as_view(template_name='send_money/choose-method.html'),
            name='choose_method'),
        url(r'^start-payment/$', views.DebitCardPrisonerDetailsView.as_view(),
            name='prisoner_details_debit'),
        url(r'^prisoner-details/$', views.BankTransferPrisonerDetailsView.as_view(),
            name='prisoner_details_bank'),
    ]
elif settings.SHOW_DEBIT_CARD_OPTION:
    urlpatterns = [
        url(r'^$', views.DebitCardPrisonerDetailsView.as_view(), name='prisoner_details_debit'),
    ]
elif settings.SHOW_BANK_TRANSFER_OPTION:
    urlpatterns = [
        url(r'^$', views.BankTransferPrisonerDetailsView.as_view(), name='prisoner_details_bank'),
    ]
else:
    urlpatterns = []

if settings.SHOW_BANK_TRANSFER_OPTION:
    urlpatterns += [
        url(r'^bank-transfer/$', views.bank_transfer_view, name='bank_transfer'),
    ]

if settings.SHOW_DEBIT_CARD_OPTION:
    urlpatterns += [
        url(r'^send-money/$', views.SendMoneyView.as_view(), name='send_money_debit'),
        url(r'^check-details/$', views.CheckDetailsView.as_view(), name='check_details'),
        url(r'^clear-session/$', views.clear_session_view, name='clear_session'),
        url(r'^card-payment/$', views.debit_card_view, name='debit_card'),
        url(r'^confirmation/$', views.confirmation_view, name='confirmation'),
    ]
