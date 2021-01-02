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
      var $questionList = $(this);
      var $questions = $questionList.find('.mtp-question');
      var $button = $('<a class="mtp-question-list__open-all" href="#"></a>');
      $button.text(django.gettext('Open all'));
      $button.attr('aria-expanded', 'false');
      $button.click(function (e) {
        e.preventDefault();
        var allOpen = $questions.filter('.mtp-question--open').length === $questions.length;
        $questions.each(function () {
          var $question = $(this);
          var open = $question.hasClass('mtp-question--open');
          if (allOpen || !open) {
            $question.find('a').click();
          }
        });
      });
      $questionList.before($button);
      $questions.find('a').click(function () {
        var allOpen = $questions.filter('.mtp-question--open').length === $questions.length;
        if (allOpen) {
          $button.text(django.gettext('Close all'));
          $button.attr('aria-expanded', 'true');
        } else {
          $button.text(django.gettext('Open all'));
          $button.attr('aria-expanded', 'false');
        }
      });
    });

    // allow linking directly to a question
    try {
      var $anchor = $(window.location.hash);
      var $button = null;
      if ($anchor.parent('.mtp-question').length) {
        // linked to question trigger element
        $button = $anchor;
      } else if ($anchor.hasClass('mtp-answer')) {
        // linked to answer
        $button = $('#' + $anchor.attr('aria-labelledby'));
      }
      if ($button) {
        $('html, body').scrollTop($button.offset().top - 15);
        $button.click();
      }
    } catch (e) {
      // eslint-disable-line no-empty
    }
  }
};
