'use strict';

exports.CookiePrompt = {
  selector: '.mtp-cookie-prompt',

  init: function () {
    var $cookiePrompt = $(this.selector);
    var $form = $cookiePrompt.find('form');
    var $buttons = $form.find('button');

    $buttons.click(function (e) {
      e.preventDefault();
      var data = $form.serializeArray();
      data.push({
        name: this.name,
        value: this.value
      });

      $.ajax({
        type: 'POST',
        url: $form.attr('action'),
        data: data,
        success: function () {
          $cookiePrompt.remove();
        }
      });
      return false;
    });

    $form.submit(function (e) {
      e.preventDefault();
      return false;
    });
  }
};
