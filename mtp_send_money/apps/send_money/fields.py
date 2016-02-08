import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.utils.translation import ugettext as _


class SplitDateWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = (forms.NumberInput(attrs=attrs),
                   forms.NumberInput(attrs=attrs),
                   forms.NumberInput(attrs=attrs),)
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.day, value.month, value.year]
        return [None, None, None]


class SplitHiddenDateWidget(SplitDateWidget):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        for widget in self.widgets:
            widget.input_type = 'hidden'


class SplitDateField(forms.MultiValueField):
    widget = SplitDateWidget
    hidden_widget = SplitHiddenDateWidget

    def __init__(self, *args, **kwargs):
        day_bounds_error = _('Ensure that the day is between 1 and 31.')
        month_bounds_error = _('Ensure that the month is between 1 and 12.')
        year_bounds_error = (_('Ensure that the year is between 1900 and %(current_year)s.')
                             % {'current_year': now().year})

        fields = [
            forms.IntegerField(min_value=1, max_value=31, error_messages={
                'min_value': day_bounds_error,
                'max_value': day_bounds_error,
                'invalid': _('Enter the day of the month as a number.')
            }),
            forms.IntegerField(min_value=1, max_value=12, error_messages={
                'min_value': month_bounds_error,
                'max_value': month_bounds_error,
                'invalid': _('Enter the month as a number.')
            }),
            forms.IntegerField(min_value=1900, max_value=now().year, error_messages={
                'min_value': year_bounds_error,
                'max_value': year_bounds_error,
                'invalid': _('Enter the year as a number.')
            }),
        ]
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            try:
                if any(item in self.empty_values for item in data_list):
                    raise ValueError
                return datetime.date(data_list[2], data_list[1], data_list[0])
            except ValueError:
                raise ValidationError(_('Enter a valid date.'))
        return None
