from django.urls import re_path

from send_money.views import (
    clear_session_view,
    UserAgreementView, PaymentMethodChoiceView,
    DebitCardPrisonerDetailsView, DebitCardAmountView, DebitCardCheckView,
    DebitCardPaymentView, DebitCardConfirmationView,
)

app_name = 'send_money'
urlpatterns = [
    re_path(
        r'^$',
        UserAgreementView.as_view(),
        name=UserAgreementView.url_name,
    ),
    re_path(
        r'^payment-choice/$',
        PaymentMethodChoiceView.as_view(),
        name=PaymentMethodChoiceView.url_name,
    ),
    re_path(
        r'^debit-card/details/$',
        DebitCardPrisonerDetailsView.as_view(),
        name=DebitCardPrisonerDetailsView.url_name,
    ),
    re_path(
        r'^debit-card/amount/$',
        DebitCardAmountView.as_view(),
        name=DebitCardAmountView.url_name,
    ),
    re_path(
        r'^debit-card/check/$',
        DebitCardCheckView.as_view(),
        name=DebitCardCheckView.url_name,
    ),
    re_path(
        r'^debit-card/payment/$',
        DebitCardPaymentView.as_view(),
        name=DebitCardPaymentView.url_name,
    ),
    re_path(
        r'^debit-card/confirmation/$',
        DebitCardConfirmationView.as_view(),
        name=DebitCardConfirmationView.url_name,
    ),

    re_path(
        r'^clear-session/$',
        clear_session_view,
        name='clear_session',
    ),

]
