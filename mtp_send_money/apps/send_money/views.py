import decimal
import logging
import random

from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.views.generic import FormView, TemplateView, View
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from send_money import forms as send_money_forms
from send_money.exceptions import GovUkPaymentStatusException
from send_money.models import PaymentMethodBankTransferEnabled as PaymentMethod
from send_money.payments import is_active_payment, GovUkPaymentStatus, PaymentClient
from send_money.utils import (
    get_link_by_rel,
    get_service_charge,
    site_url,
    get_requests_exception_for_logging,
)

logger = logging.getLogger('mtp')


def build_view_url(request, url_name):
    url_name = '%s:%s' % (request.resolver_match.namespace, url_name)
    return reverse(url_name)


def clear_session_view(request):
    """
    View that clears the session and restarts the user flow.
    @param request: the HTTP request
    """
    request.session.flush()
    return redirect(build_view_url(request, UserAgreementView.url_name))


def get_payment_delayed_capture_rollout_percentage():
    """
    TODO: remove following delayed capture release
    """
    try:
        rollout_perc = int(settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE)
        if rollout_perc < 0 or rollout_perc > 100:
            raise ValueError()
    except ValueError:
        logger.error(
            'PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE should be a number between 0 and 100, '
            f'found {settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE} instead. '
            'Disabling delayed capture for now.'
        )
        rollout_perc = 0
    return rollout_perc


def should_be_capture_delayed():
    """
    Util function to roll out delayed payment capture gradually in order to limit damage caused by unknown problems.
    Returns True if the payment should be created with delayed_capture == True with a chance in
    percentage equal to settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE.

    TODO remove (and always delay) or allow just an on/off value when happy and confident that things are
    working fine.
    """
    rollout_perc = get_payment_delayed_capture_rollout_percentage()

    if rollout_perc == 0:
        return False

    if rollout_perc == 100:
        return True

    chance = random.randint(1, 100)
    return chance <= rollout_perc


class SendMoneyView(View):
    previous_view = None
    payment_method = None

    @classmethod
    def get_previous_views(cls, view):
        if view.previous_view:
            yield from cls.get_previous_views(view.previous_view)
            yield view.previous_view

    @classmethod
    def is_service_charged(cls):
        zero = decimal.Decimal('0')
        return (
            settings.SERVICE_CHARGE_PERCENTAGE > zero or
            settings.SERVICE_CHARGE_FIXED > zero
        )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.valid_form_data = {}

    def dispatch(self, request, *args, **kwargs):
        for view in self.get_previous_views(self):
            if not hasattr(view, 'form_class') or not view.is_form_enabled():
                continue
            form = view.form_class.unserialise_from_session(request)
            if form.is_valid():
                self.valid_form_data[view.url_name] = form.cleaned_data
            else:
                return redirect(build_view_url(self.request, view.url_name))
        # if choose method form has been used and we are in the wrong flow, redirect
        method_choice = self.valid_form_data.get(PaymentMethodChoiceView.url_name)
        if (method_choice and self.payment_method and
                method_choice['payment_method'] != self.payment_method.name):
            return redirect(build_view_url(self.request, PaymentMethodChoiceView.url_name))
        return super().dispatch(request, *args, **kwargs)


class SendMoneyFormView(SendMoneyView, FormView):
    @classmethod
    def is_form_enabled(cls):
        return True

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        if self.request.method == 'GET':
            form = self.form_class.unserialise_from_session(self.request)
            if form.is_valid():
                # valid form found in session so restore it
                context_data['form'] = form
        return context_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        # save valid form to session
        form.serialise_to_session()
        return super().form_valid(form)


class UserAgreementView(SendMoneyView, TemplateView):
    url_name = 'user_agreement'
    template_name = 'send_money/user-agreement.html'

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['breadcrumbs_back'] = settings.START_PAGE_URL
        return context_data

    def get_success_url(self):
        return build_view_url(self.request, PaymentMethodChoiceView.url_name)


class PaymentMethodChoiceView(SendMoneyFormView):
    url_name = 'choose_method'
    previous_view = UserAgreementView
    template_name = 'send_money/payment-method.html'
    form_class = send_money_forms.PaymentMethodChoiceForm

    def dispatch(self, request, *args, **kwargs):
        # reset the session so that we can start fresh
        if not request.session.is_empty():
            request.session.flush()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if form.cleaned_data['payment_method'] == PaymentMethod.bank_transfer.name:
            return HttpResponseBadRequest('Bank Transfers are no longer supported by this service')

        self.success_url = build_view_url(self.request, DebitCardPrisonerDetailsView.url_name)
        return super().form_valid(form)


class DebitCardFlowException(Exception):
    pass


class DebitCardFlow(SendMoneyView):
    payment_method = PaymentMethod.debit_card


class DebitCardPrisonerDetailsView(DebitCardFlow, SendMoneyFormView):
    url_name = 'prisoner_details_debit'
    previous_view = PaymentMethodChoiceView
    template_name = 'send_money/debit-card-prisoner-details.html'
    form_class = send_money_forms.DebitCardPrisonerDetailsForm

    def get_success_url(self):
        return build_view_url(self.request, DebitCardAmountView.url_name)


class DebitCardAmountView(DebitCardFlow, SendMoneyFormView):
    url_name = 'send_money_debit'
    previous_view = DebitCardPrisonerDetailsView
    template_name = 'send_money/debit-card-amount.html'
    form_class = send_money_forms.DebitCardAmountForm

    def get_context_data(self, **kwargs):
        kwargs['service_charged'] = self.is_service_charged()
        if kwargs['service_charged']:
            kwargs.update({
                'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
                'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
                'sample_amount': 20,  # in pounds
            })
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        return build_view_url(self.request, DebitCardCheckView.url_name)

    def get_form_kwargs(self):
        return dict(
            super().get_form_kwargs(),
            prisoner_number=self.valid_form_data[DebitCardPrisonerDetailsView.url_name]['prisoner_number']
        )


class DebitCardCheckView(DebitCardFlow, TemplateView):
    url_name = 'check_details'
    previous_view = DebitCardAmountView
    template_name = 'send_money/debit-card-check.html'

    def get_context_data(self, **kwargs):
        prisoner_details = self.valid_form_data[DebitCardPrisonerDetailsView.url_name]
        amount_details = self.valid_form_data[DebitCardAmountView.url_name]
        kwargs.update(**prisoner_details)
        kwargs.update(**amount_details)
        return super().get_context_data(service_charged=self.is_service_charged(), **kwargs)

    def get_prisoner_details_url(self):
        return build_view_url(self.request, DebitCardPrisonerDetailsView.url_name)

    def get_amount_url(self):
        return build_view_url(self.request, DebitCardAmountView.url_name)

    def get_success_url(self):
        return build_view_url(self.request, DebitCardPaymentView.url_name)


class DebitCardPaymentView(DebitCardFlow):
    url_name = 'debit_card'
    previous_view = DebitCardCheckView

    def get(self, request):
        prisoner_details = self.valid_form_data[DebitCardPrisonerDetailsView.url_name]
        amount_details = self.valid_form_data[DebitCardAmountView.url_name]

        amount_pence = int(amount_details['amount'] * 100)
        service_charge_pence = int(get_service_charge(amount_details['amount']) * 100)
        user_ip = request.META.get('HTTP_X_FORWARDED_FOR', '')
        user_ip = user_ip.split(',')[0].strip() or None

        payment_ref = None
        failure_context = {
            'short_payment_ref': _('Not known')
        }
        try:
            payment_client = PaymentClient()
            new_payment = {
                'amount': amount_pence,
                'service_charge': service_charge_pence,
                'recipient_name': prisoner_details['prisoner_name'],
                'prisoner_number': prisoner_details['prisoner_number'],
                'prisoner_dob': prisoner_details['prisoner_dob'].isoformat(),
                'ip_address': user_ip,
            }
            payment_ref = payment_client.create_payment(new_payment)
            failure_context['short_payment_ref'] = payment_ref[:8]

            new_govuk_payment = {
                'delayed_capture': should_be_capture_delayed(),
                'amount': amount_pence + service_charge_pence,
                'reference': payment_ref,
                'description': gettext('To this prisoner: %(prisoner_number)s' % prisoner_details),
                'return_url': site_url(
                    build_view_url(self.request, DebitCardConfirmationView.url_name)
                ) + '?payment_ref=' + payment_ref,
            }
            if new_govuk_payment['delayed_capture']:
                logger.info('Starting delayed capture for %(payment_ref)s', {'payment_ref': payment_ref})

            govuk_payment = payment_client.create_govuk_payment(payment_ref, new_govuk_payment)
            if govuk_payment:
                return redirect(get_link_by_rel(govuk_payment, 'next_url'))
        except OAuth2Error:
            logger.exception('Authentication error')
        except RequestException:
            logger.exception('Failed to create new payment (ref %s)', payment_ref)

        return render(request, 'send_money/debit-card-error.html', failure_context)


class DebitCardConfirmationView(TemplateView):
    url_name = 'confirmation'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status = GovUkPaymentStatus.error

    def get_template_names(self):
        if self.status == GovUkPaymentStatus.success:
            return ['send_money/debit-card-confirmation.html']
        if self.status == GovUkPaymentStatus.capturable:
            return ['send_money/debit-card-on-hold.html']
        return ['send_money/debit-card-error.html']

    def get(self, request, *args, **kwargs):
        payment_ref = self.request.GET.get('payment_ref')
        if not payment_ref:
            return clear_session_view(request)
        kwargs['short_payment_ref'] = payment_ref[:8].upper()
        try:
            # check payment status
            payment_client = PaymentClient()
            payment = payment_client.get_payment(payment_ref)

            # only continue if:
            # - the MTP payment is in pending (it moves to the 'taken' state by the cronjob x mins after
            #   the gov.uk payment succeeds)
            #   OR
            # - the MTP payment is in the 'taken' state (by the cronjob x mins after the gov.uk payment succeeded)
            #   but only for a limited period of time
            if not payment or not is_active_payment(payment):
                return clear_session_view(request)

            kwargs.update({
                'prisoner_name': payment['recipient_name'],
                'prisoner_number': payment['prisoner_number'],
                'amount': decimal.Decimal(payment['amount']) / 100,
            })

            if payment['status'] == 'taken':
                self.status = GovUkPaymentStatus.success
            else:
                # check gov.uk payment status
                govuk_id = payment['processor_id']
                govuk_payment = payment_client.get_govuk_payment(govuk_id)

                self.status = payment_client.complete_payment_if_necessary(payment, govuk_payment)

                # here status can be either created, started, submitted, capturable, success, failed, cancelled, error
                # or None

                error_code = govuk_payment and govuk_payment.get('state', {}).get('code')

                # payment was cancelled programmatically (this would not currently happen)
                if self.status == GovUkPaymentStatus.cancelled:
                    # error_code is expected to be P0040
                    error_code == 'P0040' or logger.error(
                        f'Unexpected code for cancelled GOV.UK Pay payment {payment_ref}: {error_code}'
                    )
                    return render(request, 'send_money/debit-card-cancelled.html')

                # the user cancelled the payment
                if self.status == GovUkPaymentStatus.failed and error_code == 'P0030':
                    return render(request, 'send_money/debit-card-cancelled.html')

                # GOV.UK Pay session expired
                if self.status == GovUkPaymentStatus.failed and error_code == 'P0020':
                    return render(request, 'send_money/debit-card-session-expired.html')

                # payment method was rejected by card issuer or processor
                # e.g. due to insufficient funds or risk management
                if self.status == GovUkPaymentStatus.failed:
                    # error_code is expected to be P0010
                    error_code == 'P0010' or logger.error(
                        f'Unexpected code for failed GOV.UK Pay payment {payment_ref}: {error_code}'
                    )
                    return render(request, 'send_money/debit-card-declined.html')

                # here status can be either created, started, submitted, capturable, success, error
                # or None

                # treat statuses created, started, submitted or None as error as they should have never got here
                if not self.status or self.status.is_awaiting_user_input():
                    self.status = GovUkPaymentStatus.error

                # here status can be either capturable, success, error

        except OAuth2Error:
            logger.exception(
                'Authentication error while processing %(payment_ref)s',
                {'payment_ref': payment_ref},
            )
            self.status = GovUkPaymentStatus.error
        except RequestException as error:
            response_content = get_requests_exception_for_logging(error)
            logger.exception(
                'Payment check failed for ref %(payment_ref)s. Received: %(response_content)s',
                {'payment_ref': payment_ref, 'response_content': response_content},
            )
            self.status = GovUkPaymentStatus.error
        except GovUkPaymentStatusException:
            logger.exception(
                'GOV.UK Pay returned unexpected status for ref %(payment_ref)s',
                {'payment_ref': payment_ref},
            )
            self.status = GovUkPaymentStatus.error

        response = super().get(request, *args, **kwargs)
        request.session.flush()
        return response
