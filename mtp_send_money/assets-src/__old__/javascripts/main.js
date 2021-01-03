(function () {
  'use strict';

  // common
  require('analytics').Analytics.init();
  require('element-focus').ElementFocus.init();
  require('year-field-completion').YearFieldCompletion.init();
  require('disclosure').Disclosure.init();

  // send-money
  require('charges').Charges.init();
  require('reference').Reference.init();
  require('filtered-list').FilteredList.init();
  require('question-list').QuestionList.init();
}());
