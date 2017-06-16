from django.conf.urls import url

from send_money.views import (
    clear_session_view,
    PaymentMethodChoiceView,
    BankTransferWarningView, BankTransferPrisonerDetailsView, BankTransferReferenceView,
    DebitCardPrisonerDetailsView, DebitCardAmountView, DebitCardCheckView,
    DebitCardPaymentView, DebitCardConfirmationView
)
from send_money.views_misc import help_view, prison_list_view

app_name = 'send_money'
urlpatterns = [
    url(r'^$', PaymentMethodChoiceView.as_view(),
        name=PaymentMethodChoiceView.url_name),

    url(r'^bank-transfer/warning/$', BankTransferWarningView.as_view(),
        name=BankTransferWarningView.url_name),
    url(r'^bank-transfer/details/$', BankTransferPrisonerDetailsView.as_view(),
        name=BankTransferPrisonerDetailsView.url_name),
    url(r'^bank-transfer/reference/$', BankTransferReferenceView.as_view(),
        name=BankTransferReferenceView.url_name),

    url(r'^debit-card/details/$', DebitCardPrisonerDetailsView.as_view(),
        name=DebitCardPrisonerDetailsView.url_name),
    url(r'^debit-card/amount/$', DebitCardAmountView.as_view(),
        name=DebitCardAmountView.url_name),
    url(r'^debit-card/check/$', DebitCardCheckView.as_view(),
        name=DebitCardCheckView.url_name),
    url(r'^debit-card/payment/$', DebitCardPaymentView.as_view(),
        name=DebitCardPaymentView.url_name),
    url(r'^debit-card/confirmation/$', DebitCardConfirmationView.as_view(),
        name=DebitCardConfirmationView.url_name),

    url(r'^help/$', help_view, name='help'),
    url(r'^help/bank-transfer-issues/$', help_view, kwargs={'page': 'bank-transfer-issues'},
        name='help_bank_transfer'),
    url(r'^help/payment-delay/$', help_view, kwargs={'page': 'payment-delay'},
        name='help_delays'),
    url(r'^help/prisoner-moved-or-released/$', help_view, kwargs={'page': 'prisoner-moved-or-released'},
        name='help_transfered'),
    url(r'^help/prisons/$', prison_list_view, name='prison_list'),

    url(r'^clear-session/$', clear_session_view, name='clear_session'),
]
