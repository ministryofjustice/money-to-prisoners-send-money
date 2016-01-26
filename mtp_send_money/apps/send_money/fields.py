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
        fields = [
            forms.IntegerField(min_value=1, max_value=31),
            forms.IntegerField(min_value=1, max_value=12),
            forms.IntegerField(min_value=1900, max_value=now().year),
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
