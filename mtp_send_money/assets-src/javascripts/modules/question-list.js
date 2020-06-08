// QNA accordion
'use strict';

// NB: will be replaced once migrated to GDS Design System
exports.QuestionList = {
  init: function () {
    // hide all answers and make icons always invisible to screen readers
    $('.mtp-question-icon, .mtp-answer').attr('aria-hidden', 'true');

    // add open/close functionality to questions
    $('.mtp-question').each(function () {
      var $question = $(this);
      var $questionButton = $question.find('a');
      var $answer = $question.next('.mtp-answer');
      $questionButton.attr({
        'aria-controls': $answer.attr('id'),
        'aria-expanded': 'false'
      });
      $questionButton.click(function (e) {
        e.preventDefault();
        var open = $question.hasClass('mtp-question--open');
        if (open) {
          $answer.hide();
          $answer.attr('aria-hidden', 'true');
          $question.removeClass('mtp-question--open');
          $questionButton.attr('aria-expanded', 'false');
        } else {
          $answer.show();
          $answer.attr('aria-hidden', 'false');
          $question.addClass('mtp-question--open');
          $questionButton.attr('aria-expanded', 'true');
        }
      });
    });

    // make it easy to see all answers
    $('.mtp-question-list').each(function () {
      var $questions = $(this);
      var $button = $('<a class="mtp-question-list__open-all" href="#"></a>');
      $button.text(django.gettext('Open all'));
      $button.click(function (e) {
        e.preventDefault();
        $questions.find('.mtp-question').each(function () {
          var $question = $(this);
          var open = $question.hasClass('mtp-question--open');
          if (!open) {
            $question.find('a').click();
          }
        });
      });
      $questions.before($button);
    });
  }
};
