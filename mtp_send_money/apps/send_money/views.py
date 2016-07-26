from functools import wraps
import logging

from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.generic import FormView
import requests
from mtp_common.email import send_email
from slumber.exceptions import SlumberHttpBaseException

from send_money.forms import SendMoneyForm, PrisonerDetailsForm
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
                    start_url = reverse('send_money:send_money_debit')
                elif settings.SHOW_BANK_TRANSFER_OPTION:
                    start_url = reverse('send_money:send_money_bank')
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


class SendMoneyBankTransferView(FormView):
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


class SendMoneyView(FormView):
    """
    The main form-filling view for sending payments
    """
    form_class = SendMoneyForm
    template_name = 'send_money/send-money.html'
    success_url = reverse_lazy('send_money:check_details')

    def get_initial(self):
        initial = super().get_initial()
        session = self.request.session
        if 'change' in self.request.GET and SendMoneyForm.session_contains_form_data(session):
            initial.update(SendMoneyForm.form_data_from_session(session))
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
            govuk_url('/payments'), headers=govuk_headers(), json=new_govuk_payment
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

    return render(request, 'send_money/failure.html', context)


def confirmation_view(request):
    """
    View that presents a confirmation message if a gov.uk payment was successful.
    NB: Clears the session
    @param request: the HTTP request
    """
    payment_ref = request.GET.get('payment_ref')
    if payment_ref is None:
        return redirect(reverse('send_money:send_money_debit'))
    context = {'success': False, 'payment_ref': payment_ref[:8]}

    try:
        client = get_api_client()
        api_response = client.payments(payment_ref).get()
        context['prisoner_name'] = api_response['recipient_name']
        context['amount'] = api_response['amount'] / 100

        govuk_id = api_response['processor_id']

        govuk_response = requests.get(
            govuk_url('/payments/%s' % govuk_id), headers=govuk_headers()
        )

        if (govuk_response.status_code == 200 and
                govuk_response.json()['state']['status'] == 'success'):
            payment_update = {
                'status': 'taken'
            }

            client.payments(payment_ref).patch(payment_update)
            context.update({
                'success': True,
            })
            if api_response.get('email'):
                send_email(
                    api_response['email'], 'send_money/email/confirmation.txt',
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
                'Failed to access payment %s' % payment_ref,
            )

    request.session.flush()
    return render(request, 'send_money/confirmation.html', context)


def clear_session_view(request):
    """
    View that clears the session and restarts the user flow.
    @param request: the HTTP request
    """
    request.session.flush()
    return redirect('send_money:send_money_debit')
