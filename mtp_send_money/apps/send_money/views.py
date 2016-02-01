from functools import wraps
import logging

from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.generic import FormView
import requests
from slumber.exceptions import SlumberHttpBaseException

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.utils import (
    unserialise_amount, unserialise_date, bank_transfer_reference,
    govuk_headers, govuk_url, get_api_client, site_url, get_link_by_rel,
    get_total_charge
)

logger = logging.getLogger('mtp')


def require_session_parameters(view):
    """
    View decorator to require a session to include the serialised form
    @param view: the view callable
    """

    @wraps(view)
    def inner(request, *args, **kwargs):
        if not SendMoneyForm.session_contains_form_data(request.session):
            return redirect(reverse('send_money:send_money'))
        return view(request, *args, **kwargs)

    return inner


def make_context_from_session(view):
    """
    View decorator that creates a template context from the serialised form
    in a session
    @param view: the view callable
    """

    @wraps(view)
    def inner(request, *args, **kwargs):
        session = request.session
        context = {field: session[field] for field in SendMoneyForm.get_field_names()}
        context['prisoner_dob'] = unserialise_date(context['prisoner_dob'])
        context['amount'] = unserialise_amount(context['amount'])
        return view(request, context, *args, **kwargs)

    return inner


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

        # TODO: remove option once TD allows showing bank transfers
        context_data['HIDE_BANK_TRANSFER_OPTION'] = settings.HIDE_BANK_TRANSFER_OPTION

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
    success_url = None

    @method_decorator(require_session_parameters)
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

    def get_success_url(self):
        if self.request.session['payment_method'] == str(PaymentMethod.bank_transfer):
            return reverse('send_money:bank_transfer')
        return reverse('send_money:debit_card')

    def form_invalid(self, form):
        return redirect(reverse('send_money:send_money') + '?change')


@require_session_parameters
@make_context_from_session
def bank_transfer_view(request, context):
    """
    View displaying details of how to set up a bank transfer.
    NB: Clears the session
    @param request: the HTTP request
    @param context: the template context
    """
    context.update({
        'payable_to': settings.NOMS_HOLDING_ACCOUNT_NAME,
        'account_number': settings.NOMS_HOLDING_ACCOUNT_NUMBER,
        'sort_code': settings.NOMS_HOLDING_ACCOUNT_SORT_CODE,
        'bank_transfer_reference': bank_transfer_reference(
            context['prisoner_number'],
            context['prisoner_dob'],
        ),
        'amount_to_pay': get_total_charge(request.session['amount']),
    })
    request.session.flush()
    return render(request, 'send_money/bank-transfer.html', context)


@require_session_parameters
@make_context_from_session
def debit_card_view(request, context):
    """
    View that initiates the gov.uk payment process and displays error responses.
    @param request: the HTTP request
    @param context: the template context
    """
    new_payment = {
        'amount': int(context['amount'] * 100),
        'recipient_name': context['prisoner_name'],
        'prisoner_number': context['prisoner_number'],
        'prisoner_dob': context['prisoner_dob'].isoformat(),
    }

    client = get_api_client()
    try:
        api_response = client.payments.post(new_payment)
        payment_ref = api_response['uuid']

        new_govuk_payment = {
            'amount': int(context['amount'] * 100),
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
                'Failed to create new GOV.UK payment for transaction %s'
                % api_response['uuid']
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
        return redirect(reverse('send_money:send_money'))
    context = {'success': False}

    try:
        client = get_api_client()
        api_response = client.payments(payment_ref).get()
        govuk_id = api_response['processor_id']

        govuk_response = requests.get(
            govuk_url('/payments/%s' % govuk_id), headers=govuk_headers()
        )

        if (govuk_response.status_code == 200 and
                govuk_response.json()['status'] == 'SUCCEEDED'):
            payment_update = {
                'status': 'taken'
            }

            client.payments(payment_ref).patch(payment_update)
            context['success'] = True
        else:
            logger.error(
                'Failed to retrieve payment status from GOV.UK for payment %s' % payment_ref
            )
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
    return redirect('send_money:send_money')
