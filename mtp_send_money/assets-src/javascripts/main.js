(function () {
  'use strict';

  require('polyfills').Polyfills.init();
  require('placeholder-polyfill').PlaceholderPolyfill.init();

  require('proposition-header').PropositionHeader.init();
  require('analytics').Analytics.init();
  require('element-focus').ElementFocus.init();
  require('year-field-completion').YearFieldCompletion.init();
  require('disclosure').Disclosure.init();

  require('charges').Charges.init();
  require('govuk-pay-connection-check').GOVUKPayConnectionCheck.init();
  require('experiments').Experiments.init();
  require('reference').Reference.init();
  require('filtered-list').FilteredList.init();
}());
