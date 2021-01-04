(function () {
  'use strict';

  // send-money
  require('charges').Charges.init();
  require('reference').Reference.init();
  require('filtered-list').FilteredList.init();
  require('question-list').QuestionList.init();
}());
