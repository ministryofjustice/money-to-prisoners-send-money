'use strict';

// design systems
import 'govuk-design-system';

// common
import {Analytics} from 'analytics';
import {ElementFocus} from 'element-focus';
import {YearFieldCompletion} from 'year-field-completion';
import {Notifications} from 'notifications';

Analytics.init();
ElementFocus.init();
YearFieldCompletion.init();
Notifications.init();

// send-money
import {Charges} from 'charges';
import {Reference} from 'reference';
import {FilteredList} from 'filtered-list';

Charges.init();
Reference.init();
FilteredList.init();
