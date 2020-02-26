'use strict';

export var Reference = {
  init: function () {
    $('.mtp-reference-actions__print').click(function (e) {
      e.preventDefault();
      try {
        window.print();
      } catch (e) {}  // eslint-disable-line
    });

    $('.mtp-reference-actions__email').click(function (e) {
      e.preventDefault();
      $('#mtp-reference-actions__email-form').show();
      $('#id_email').focus();
    });
  }
};
