import datetime
import decimal
import unittest

from django.core.exceptions import ValidationError


from send_money.utils import serialise_amount, unserialise_amount, \
    serialise_date, unserialise_date, \
    validate_prisoner_number, bank_transfer_reference


class AmountSerialisationTestCase(unittest.TestCase):
    def test_amount_serialisation(self):
        self.assertEqual(serialise_amount(decimal.Decimal('1')), '1.00')
        self.assertEqual(serialise_amount(decimal.Decimal(1)), '1.00')
        self.assertEqual(serialise_amount(decimal.Decimal('1000')), '1000.00')

    def test_amount_unserialisation(self):
        self.assertEqual(unserialise_amount('1.00'), decimal.Decimal('1'))
        self.assertEqual(unserialise_amount('1.00'), decimal.Decimal('1.00'))
        self.assertEqual(unserialise_amount('1000.00'), decimal.Decimal('1000'))


class DateSerialisationTestCase(unittest.TestCase):
    def test_date_serialisation(self):
        self.assertEqual(serialise_date(datetime.date(2016, 1, 14)), '2016-01-14')

    def test_date_unserialisation(self):
        self.assertEqual(unserialise_date('2016-01-14'), datetime.date(2016, 1, 14))


class ValidationTestCase(unittest.TestCase):
    def test_valid_prisoner_number_validation(self):
        validate_prisoner_number('A1234AB')
        # case is ignored, but number is sent to api as uppercase
        validate_prisoner_number('a1234ab')

    def test_invalid_prisoner_number_validation(self):
        with self.assertRaises(ValidationError):
            validate_prisoner_number('')
        with self.assertRaises(ValidationError):
            validate_prisoner_number('1234567')


class BankTransferReference(unittest.TestCase):
    def test_bank_transfer_reference(self):
        self.assertEqual(
            bank_transfer_reference('AB1234AB', datetime.date(1980, 1, 4)),
            'AB1234AB 04/01/1980',
        )
