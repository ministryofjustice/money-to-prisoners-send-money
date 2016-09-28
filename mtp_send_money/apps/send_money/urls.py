from django.conf.urls import url

from send_money.views import (
    clear_session_view, help_view,
    PaymentMethodChoiceView,
    BankTransferWarningView, BankTransferPrisonerDetailsView, BankTransferReferenceView,
    DebitCardPrisonerDetailsView, DebitCardAmountView, DebitCardCheckView,
    DebitCardPaymentView, DebitCardConfirmationView
)

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

    url(r'^clear-session/$', clear_session_view, name='clear_session'),
]
