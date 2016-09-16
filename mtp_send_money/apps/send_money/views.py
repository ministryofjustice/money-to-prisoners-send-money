import datetime
from functools import wraps
import logging
import random

from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.generic import FormView
import requests
from requests.exceptions import Timeout
from mtp_common.email import send_email
from slumber.exceptions import SlumberHttpBaseException

from send_money.forms import (
    PaymentMethodForm, SendMoneyForm, PrisonerDetailsForm, StartPaymentPrisonerDetailsForm
)
from send_money.utils import (
    unserialise_amount, unserialise_date, bank_transfer_reference,
    govuk_headers, govuk_url, get_api_client, site_url, get_link_by_rel,
    get_service_charge
)

logger = logging.getLogger('mtp')


def require_session_parameters(form_class):
    """
    View decorator to require a session to include the serialised form
    @param view: the view callable
    """

    def wrapper(view):
        @wraps(view)
        def inner(request, *args, **kwargs):
            if not form_class.session_contains_form_data(request.session):
                if settings.SHOW_DEBIT_CARD_OPTION and settings.SHOW_BANK_TRANSFER_OPTION:
                    start_url = reverse('send_money:choose_method')
                elif settings.SHOW_DEBIT_CARD_OPTION:
                    start_url = reverse('send_money:prisoner_details_debit')
                elif settings.SHOW_BANK_TRANSFER_OPTION:
                    start_url = reverse('send_money:prisoner_details_bank')
                return redirect(start_url)
            return view(request, *args, **kwargs)
        return inner

    return wrapper


def make_context_from_session(form_class):
    """
    View decorator that creates a template context from the serialised form
    in a session
    @param view: the view callable
    """

    def wrapper(view):
        @wraps(view)
        def inner(request, *args, **kwargs):
            session = request.session
            context = {field: session[field] for field in form_class.get_field_names()}
            if 'prisoner_dob' in context:
                context['prisoner_dob'] = unserialise_date(context['prisoner_dob'])
            if 'amount' in context:
                context['amount'] = unserialise_amount(context['amount'])
            return view(request, context, *args, **kwargs)
        return inner

    return wrapper


class BankTransferPrisonerDetailsView(FormView):
    form_class = PrisonerDetailsForm
    template_name = 'send_money/bank-transfer-form.html'
    success_url = reverse_lazy('send_money:bank_transfer')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.save_form_data_in_session(self.request.session)
        return super().form_valid(form)


class ChooseMethodView(FormView):
    template_name = 'send_money/choose-method.html'
    form_class = PaymentMethodForm
    experiment_cookie_name = 'EXP-first-payment-choice'
    experiment_variations = ['debit-card', 'bank-transfer']
    experiment_lifetime = datetime.timedelta(days=300)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.show_bank_transfer_first = False
        self.set_experiment_cookie = None

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if self.set_experiment_cookie is not None:
            response.set_cookie(self.experiment_cookie_name, self.set_experiment_cookie,
                                expires=timezone.now() + self.experiment_lifetime)
        return response

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
            'service_charged': settings.SERVICE_CHARGED,
            'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
            'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
        })
        return context_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['show_bank_transfer_first'] = self.show_bank_transfer_first
        return kwargs

    def form_valid(self, form):
        return redirect(form.chosen_view_name)


class DebitCardPrisonerDetailsView(FormView):
    form_class = StartPaymentPrisonerDetailsForm
    template_name = 'send_money/debit-card-form.html'
    success_url = reverse_lazy('send_money:send_money_debit')

    def get_initial(self):
        initial = super().get_initial()
        session = self.request.session
        if 'change' in self.request.GET and StartPaymentPrisonerDetailsForm.session_contains_form_data(session):
            initial.update(StartPaymentPrisonerDetailsForm.form_data_from_session(session))
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.save_form_data_in_session(self.request.session)
        return super().form_valid(form)

    def get_success_url(self):
        success_url = super().get_success_url()
        if 'change' in self.request.GET:
            success_url += '?change=1'
        return success_url


class SendMoneyView(FormView):
    """
    The main form-filling view for sending payments
    """
    form_class = SendMoneyForm
    template_name = 'send_money/send-money.html'
    success_url = reverse_lazy('send_money:check_details')

    @method_decorator(require_session_parameters(StartPaymentPrisonerDetailsForm))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        session = self.request.session
        if 'change' in self.request.GET and SendMoneyForm.session_contains_form_data(session):
            initial.update(SendMoneyForm.form_data_from_session(session))
        else:
            initial.update(StartPaymentPrisonerDetailsForm.form_data_from_session(session))
        return initial

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        sample_amount = 20  # in pounds
        context_data.update({
            'service_charged': settings.SERVICE_CHARGED,
            'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
            'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
            'sample_amount': sample_amount,
        })

        return context_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.save_form_data_in_session(self.request.session)
        return super().form_valid(form)


class CheckDetailsView(SendMoneyView):
    """
    The form-previewing view
    """
    template_name = 'send_money/check-details.html'
    success_url = reverse_lazy('send_money:debit_card')

    @method_decorator(require_session_parameters(SendMoneyForm))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(SendMoneyForm.form_data_from_session(self.request.session))
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.switch_to_hidden()
        return form

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['preview'] = True
        return context_data

    def form_valid(self, form):
        form.save_form_data_in_session(self.request.session)
        if 'change' in self.request.POST:
            # pressed back
            return self.form_invalid(form)
        # pressed continue
        return super().form_valid(form)

    def form_invalid(self, form):
        return redirect(reverse('send_money:send_money_debit') + '?change')


@require_session_parameters(PrisonerDetailsForm)
@make_context_from_session(PrisonerDetailsForm)
def bank_transfer_view(request, context):
    """
    View displaying details of how to set up a bank transfer.
    NB: Clears the session
    @param request: the HTTP request
    @param context: the template context
    """
    context.update({
        'account_number': settings.NOMS_HOLDING_ACCOUNT_NUMBER,
        'sort_code': settings.NOMS_HOLDING_ACCOUNT_SORT_CODE,
        'bank_transfer_reference': bank_transfer_reference(
            context['prisoner_number'],
            context['prisoner_dob'],
        ),
    })
    request.session.flush()
    return render(request, 'send_money/bank-transfer.html', context)


@require_session_parameters(SendMoneyForm)
@make_context_from_session(SendMoneyForm)
def debit_card_view(request, context):
    """
    View that initiates the gov.uk payment process and displays error responses.
    @param request: the HTTP request
    @param context: the template context
    """
    amount_pence = int(context['amount'] * 100)
    service_charge_pence = int(get_service_charge(context['amount']) * 100)
    new_payment = {
        'amount': amount_pence,
        'service_charge': service_charge_pence,
        'recipient_name': context['prisoner_name'],
        'prisoner_number': context['prisoner_number'],
        'prisoner_dob': context['prisoner_dob'].isoformat(),
    }
    if context.get('email'):
        new_payment['email'] = context['email']

    client = get_api_client()
    try:
        api_response = client.payments.post(new_payment)
        payment_ref = api_response['uuid']
        context['payment_ref'] = payment_ref[:8]

        new_govuk_payment = {
            'amount': amount_pence + service_charge_pence,
            'reference': payment_ref,
            'description': _('Payment to prisoner %(prisoner_number)s'
                             % {'prisoner_number': context['prisoner_number']}),
            'return_url': site_url(
                reverse('send_money:confirmation') + '?payment_ref=' + payment_ref
            ),
        }

        govuk_response = requests.post(
            govuk_url('/payments'), headers=govuk_headers(),
            json=new_govuk_payment, timeout=15
        )

        if govuk_response.status_code == 201:
            govuk_data = govuk_response.json()
            payment_update = {
                'processor_id': govuk_data['payment_id']
            }
            client.payments(payment_ref).patch(payment_update)
            return redirect(get_link_by_rel(govuk_data, 'next_url')['href'])
        else:
            logger.error(
                'Failed to create new GOV.UK payment for transaction %s. Received: %s'
                % (api_response['uuid'], govuk_response.content)
            )
    except SlumberHttpBaseException:
        logger.exception('Failed to create new payment')
    except Timeout:
        logger.exception(
            'GOV.UK Pay payment initiation timed out for %s' % payment_ref
        )

    return render(request, 'send_money/failure.html', context)


def confirmation_view(request):
    """
    View that presents a confirmation message if a gov.uk payment was successful.
    NB: Clears the session
    @param request: the HTTP request
    """
    payment_ref = request.GET.get('payment_ref')
    if payment_ref is None:
        return redirect(reverse('send_money:prisoner_details_debit'))
    context = {'success': False, 'payment_ref': payment_ref[:8]}

    try:
        client = get_api_client()
        api_response = client.payments(payment_ref).get()
        context['prisoner_name'] = api_response['recipient_name']
        context['amount'] = api_response['amount'] / 100

        govuk_id = api_response['processor_id']

        govuk_response = requests.get(
            govuk_url('/payments/%s' % govuk_id), headers=govuk_headers(),
            timeout=15
        )

        if (govuk_response.status_code == 200 and
                govuk_response.json()['state']['status'] == 'success'):
            payment_update = {
                'status': 'taken'
            }
            email = govuk_response.json().get('email')
            if email:
                payment_update['email'] = email

            client.payments(payment_ref).patch(payment_update)
            context.update({
                'success': True,
            })
            if email:
                send_email(
                    email, 'send_money/email/confirmation.txt',
                    _('Send money to a prisoner: your payment was successful'), context=context,
                    html_template='send_money/email/confirmation.html'
                )
        else:
            logger.error(
                'Failed to retrieve payment status from GOV.UK for payment %s' % payment_ref
            )
            return clear_session_view(request)
    except SlumberHttpBaseException:
        logger.exception(
            'Failed to access payment %s' % payment_ref
        )
    except Timeout:
        logger.exception(
            'GOV.UK Pay payment status update timed out for %s' % payment_ref
        )

    request.session.flush()
    return render(request, 'send_money/confirmation.html', context)


def clear_session_view(request):
    """
    View that clears the session and restarts the user flow.
    @param request: the HTTP request
    """
    request.session.flush()
    return redirect('/')
