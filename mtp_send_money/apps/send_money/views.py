import datetime
import decimal
import logging
import random

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext, gettext_lazy as _
from django.views.generic import FormView, TemplateView, View
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from send_money import forms as send_money_forms
from send_money.models import PaymentMethod
from send_money.payments import is_active_payment, PaymentClient, PaymentStatus
from send_money.mail import send_email_for_bank_transfer_reference
from send_money.utils import (
    bank_transfer_reference,
    get_link_by_rel,
    get_service_charge,
    site_url,
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
    return redirect(build_view_url(request, PaymentMethodChoiceView.url_name))


def should_be_capture_delayed():
    """
    Util function to roll out delayed payment capture gradually in order to limit damage caused by unknown problems.
    Returns True if the payment should be created with delayed_capture == True with a chance in
    percentage uqual to settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE.

    TODO remove (and always delay) or allow just an on/off value when happy and confident that things are
    working fine.
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


class PaymentMethodChoiceView(SendMoneyFormView):
    url_name = 'choose_method'
    template_name = 'send_money/payment-method.html'
    form_class = send_money_forms.PaymentMethodChoiceForm
    experiment_cookie_name = 'EXP-first-payment-choice'
    experiment_variations = ['debit-card', 'bank-transfer']
    experiment_lifetime = datetime.timedelta(days=300)

    @classmethod
    def is_form_enabled(cls):
        return settings.SHOW_BANK_TRANSFER_OPTION and settings.SHOW_DEBIT_CARD_OPTION

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.show_bank_transfer_first = False
        self.set_experiment_cookie = None

    def dispatch(self, request, *args, **kwargs):
        # reset the session so that we can start fresh
        if not request.session.is_empty():
            request.session.flush()

        if settings.SHOW_BANK_TRANSFER_OPTION and settings.SHOW_DEBIT_CARD_OPTION:
            response = super().dispatch(request, *args, **kwargs)
            if self.set_experiment_cookie is not None:
                response.set_cookie(self.experiment_cookie_name, self.set_experiment_cookie,
                                    expires=timezone.now() + self.experiment_lifetime)
            return response
        if settings.SHOW_BANK_TRANSFER_OPTION:
            return redirect(build_view_url(self.request, BankTransferWarningView.url_name))
        if settings.SHOW_DEBIT_CARD_OPTION:
            return redirect(build_view_url(self.request, DebitCardPrisonerDetailsView.url_name))
        return redirect('submit_ticket')

    def get_experiment(self):
        experiment = {
            'show_bank_transfer_first': self.show_bank_transfer_first,
        }
        if not settings.ENABLE_PAYMENT_CHOICE_EXPERIMENT:
            return experiment

        variation = self.request.COOKIES.get(self.experiment_cookie_name)
        if variation not in self.experiment_variations:
            variation = random.choice(self.experiment_variations)
            self.set_experiment_cookie = variation
            context = 'pageview,/_experiments/display-payment-methods/%s/' % variation
        else:
            context = 'pageview,/_experiments/redisplay-payment-methods/%s/' % variation
        self.show_bank_transfer_first = variation == 'bank-transfer'

        experiment.update({
            'show_bank_transfer_first': self.show_bank_transfer_first,
            'context': context,
        })
        return experiment

    def get_context_data(self, **kwargs):
        experiment = self.get_experiment()
        context_data = super().get_context_data(**kwargs)
        context_data.update({
            'experiment': experiment,
            'service_charged': self.is_service_charged(),
            'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
            'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
        })
        return context_data

    def get_form_kwargs(self):
        kwargs = {
            **super().get_form_kwargs(),

            'show_bank_transfer_first': self.show_bank_transfer_first,
            'check_debit_card_payment_availability': True,
        }
        return kwargs

    def form_valid(self, form):
        if form.cleaned_data['payment_method'] == PaymentMethod.bank_transfer.name:
            self.success_url = build_view_url(self.request, BankTransferWarningView.url_name)
        else:
            self.success_url = build_view_url(self.request, DebitCardPrisonerDetailsView.url_name)
        return super().form_valid(form)


# BANK TRANSFER FLOW


class BankTransferFlow(SendMoneyView):
    payment_method = PaymentMethod.bank_transfer

    def dispatch(self, request, *args, **kwargs):
        if not settings.SHOW_BANK_TRANSFER_OPTION:
            raise Http404('Bank transfers are not available')
        return super().dispatch(request, *args, **kwargs)


class BankTransferWarningView(BankTransferFlow, TemplateView):
    url_name = 'bank_transfer_warning'
    previous_view = PaymentMethodChoiceView
    template_name = 'send_money/bank-transfer-warning.html'

    def get_success_url(self):
        return build_view_url(self.request, BankTransferPrisonerDetailsView.url_name)


class BankTransferPrisonerDetailsView(BankTransferFlow, SendMoneyFormView):
    url_name = 'prisoner_details_bank'
    previous_view = BankTransferWarningView
    template_name = 'send_money/bank-transfer-prisoner-details.html'
    form_class = send_money_forms.BankTransferPrisonerDetailsForm

    def get_success_url(self):
        return build_view_url(self.request, BankTransferReferenceView.url_name)


class BankTransferReferenceView(BankTransferFlow, SendMoneyFormView):
    url_name = 'bank_transfer'
    previous_view = BankTransferPrisonerDetailsView
    template_name = 'send_money/bank-transfer-reference.html'
    form_class = send_money_forms.BankTransferEmailForm

    def dispatch(self, request, *args, **kwargs):
        now = timezone.now()
        expires = request.session.get('expires')
        if not expires:
            request.session['expires'] = format_date(
                now + datetime.timedelta(minutes=settings.CONFIRMATION_EXPIRES), 'c'
            )
        elif parse_datetime(expires) < now:
            return clear_session_view(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        prisoner_details = self.valid_form_data[BankTransferPrisonerDetailsView.url_name]
        context_data.update({
            'account_number': settings.NOMS_HOLDING_ACCOUNT_NUMBER,
            'sort_code': settings.NOMS_HOLDING_ACCOUNT_SORT_CODE,
            'bank_transfer_reference': bank_transfer_reference(
                prisoner_details['prisoner_number'],
                prisoner_details['prisoner_dob'],
            ),
        })
        return context_data

    def form_valid(self, form):
        email = form.cleaned_data['email']
        context = self.get_context_data()
        context.pop('form', None)
        context.pop('view', None)

        send_email_for_bank_transfer_reference(email, context)
        return super().form_valid(form)

    def get_success_url(self):
        return build_view_url(self.request, self.url_name)


# DEBIT CARD FLOW


class DebitCardFlowException(Exception):
    pass


class DebitCardFlow(SendMoneyView):
    payment_method = PaymentMethod.debit_card

    def dispatch(self, request, *args, **kwargs):
        if not settings.SHOW_DEBIT_CARD_OPTION:
            raise Http404('Debit cards are not available')
        return super().dispatch(request, *args, **kwargs)


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
        kwargs.update({
            'service_charged': self.is_service_charged(),
            'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
            'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
            'sample_amount': 20,  # in pounds
        })
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        return build_view_url(self.request, DebitCardCheckView.url_name)


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
                logger.info(f'Starting delayed capture for {payment_ref}')

            govuk_payment = payment_client.create_govuk_payment(payment_ref, new_govuk_payment)
            if govuk_payment:
                return redirect(get_link_by_rel(govuk_payment, 'next_url'))
        except OAuth2Error:
            logger.exception('Authentication error')
        except RequestException:
            logger.exception('Failed to create new payment (ref %s)' % payment_ref)

        return render(request, 'send_money/debit-card-failure.html', failure_context)


class DebitCardConfirmationView(TemplateView):
    url_name = 'confirmation'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status = PaymentStatus.failed

    def get_template_names(self):
        if self.status == PaymentStatus.success:
            return ['send_money/debit-card-confirmation.html']
        if self.status == PaymentStatus.capturable:
            return ['send_money/debit-card-on-hold.html']
        return ['send_money/debit-card-failure.html']

    def dispatch(self, request, *args, **kwargs):
        if not settings.SHOW_DEBIT_CARD_OPTION:
            raise Http404('Debit cards are not available')
        return super().dispatch(request, *args, **kwargs)

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
                self.status = PaymentStatus.success
            else:
                # check gov.uk payment status
                govuk_id = payment['processor_id']
                govuk_payment = payment_client.get_govuk_payment(govuk_id)

                # check payment and send confirmation email if successful
                self.status = payment_client.complete_payment_if_necessary(
                    payment, govuk_payment, kwargs
                )

                # if status is error, failed or cancelled, redirect back to the start
                # as GOV.UK Pay has already shown an error page.
                if self.status.finished_and_failed():
                    return redirect(build_view_url(self.request, DebitCardCheckView.url_name))

                # here status can be either created, started, submitted, success, capturable

                # treat statuses created, started, submitted as failed as they should have
                # never got here
                if self.status.is_awaiting_user_input():
                    self.status = PaymentStatus.failed

        except OAuth2Error:
            logger.exception('Authentication error while processing %s' % payment_ref)
            self.status = PaymentStatus.failed
        except RequestException as error:
            error_message = 'Payment check failed for ref %s' % payment_ref
            if hasattr(error, 'response') and hasattr(error.response, 'content'):
                error_message += '\nReceived: %s' % error.response.content
            logger.exception(error_message)
            self.status = PaymentStatus.failed

        response = super().get(request, *args, **kwargs)
        request.session.flush()
        return response
