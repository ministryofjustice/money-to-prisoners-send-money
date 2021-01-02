// Filter-as-you-type lists
'use strict';

exports.FilteredList = {
  init: function () {
    $('.mtp-filtered-list__input').each(this.bind);
  },

  bind: function () {
    var $input = $(this);
    var placeholderText = $input.attr('placeholder') || '';
    var $list = $input.closest('.mtp-filtered-list').find('.mtp-filtered-list__list');
    var hiddenClass = 'mtp-filtered-list__hidden-item';
    var emptyItemClass = 'mtp-filtered-list__empty';
    var stopWords = null;

    if ($list.length) {
      stopWords = new RegExp('\\b' + $list.data('stop-words').split(/\s+/).join('\\b|\\b') + '\\b', 'ig');
    }

    function strip (text) {
      // collapse and trim whitespace
      return $.trim(text.replace(/\s+/g, ' '));
    }

    function normalise (text) {
      // normalise search term
      if (text === placeholderText) {
        return '';
      }
      text = strip(text).toLowerCase();
      if (stopWords) {
        // delete stop words
        text = strip(text.replace(stopWords, ''));
      }
      return text;
    }

    $input.on('keyup change click', function () {
      var searchTerm = normalise($input.val() || '');
      var listElement = $list[0];
      var $listItems = $('li', listElement);
      var $emptyItem = $('.' + emptyItemClass, listElement);
      var hiddenCount = 0;

      if (searchTerm.length < 1) {
        // cleared
        $listItems.removeClass(hiddenClass);
        $emptyItem.hide();
      } else {
        // search
        $listItems.each(function () {
          var $item = $(this);
          if ($item.hasClass(emptyItemClass)) {
            return;
          }
          if ($item.text().toLowerCase().indexOf(searchTerm) >= 0) {
            $item.removeClass(hiddenClass);
          } else {
            $item.addClass(hiddenClass);
            hiddenCount++;
          }
        });
        if (hiddenCount === $listItems.length - $emptyItem.length) {
          $emptyItem.show();
        }
      }
    });
  }
};
