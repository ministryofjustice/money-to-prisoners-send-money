from django.conf.urls import url

from send_money.views import (
    clear_session_view,
    UserAgreementView, PaymentMethodChoiceView,
    DebitCardPrisonerDetailsView, DebitCardAmountView, DebitCardCheckView,
    DebitCardPaymentView, DebitCardConfirmationView,
)

app_name = 'send_money'
urlpatterns = [
    url(r'^$', UserAgreementView.as_view(),
        name=UserAgreementView.url_name),
    url(r'^payment-choice/$', PaymentMethodChoiceView.as_view(),
        name=PaymentMethodChoiceView.url_name),
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

    url(r'^clear-session/$', clear_session_view, name='clear_session'),
]
