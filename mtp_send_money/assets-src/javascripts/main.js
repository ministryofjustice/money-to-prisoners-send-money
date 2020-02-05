'use strict';

// design systems
import 'govuk-design-system';

// common
import {Analytics} from 'analytics';
import {Banner} from 'banner';
import {ElementFocus} from 'element-focus';
import {YearFieldCompletion} from 'year-field-completion';

Analytics.init();
Banner.init();
ElementFocus.init();
YearFieldCompletion.init();

// send-money
import {FilteredList} from 'filtered-list';
import {Reference} from 'reference';
import {ServiceCharge} from 'service-charge';

FilteredList.init();
Reference.init();
ServiceCharge.init();
