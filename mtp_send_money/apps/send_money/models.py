from enum import Enum

from django.utils.translation import ugettext_lazy as _


class PaymentMethod(Enum):
    debit_card = _('Pay now by debit card (currently HMP Bullingdon and HMP Cardiff only)')
    bank_transfer = _('Get a prisoner reference to use in a UK bank transfer')

    def __str__(self):
        return self.name

    @classmethod
    def django_choices(cls):
        return tuple((option.name, option.value) for option in cls)

    @classmethod
    def lookup_description(cls, payment_method):
        if not isinstance(payment_method, cls):
            payment_method = cls[payment_method]
        return payment_method.value
