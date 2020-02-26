'use strict';

// design systems
import {initAll} from 'govuk-frontend';
initAll();

// mtp-common
import {Analytics} from 'mtp/components/analytics';
import {Banner} from 'mtp/components/banner';
import {ElementFocus} from 'mtp/components/element-focus';
import {YearFieldCompletion} from 'mtp/components/year-field-completion';

Analytics.init();
Banner.init();
ElementFocus.init();
YearFieldCompletion.init();

// send-money
import {FilteredList} from './components/filtered-list';
import {Reference} from './components/reference-page';
import {ServiceCharge} from './components/service-charge';

FilteredList.init();
Reference.init();
ServiceCharge.init();
