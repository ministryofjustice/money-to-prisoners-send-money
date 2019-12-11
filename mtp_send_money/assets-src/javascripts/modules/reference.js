// Reference section
'use strict';

export var Reference = {
  init: function () {
    $('.mtp-print-reference').click(function (e) {
      e.preventDefault();
      try {
        window.print();
      } catch (e) {}  // eslint-disable-line
    });

    $('.mtp-email-reference').click(function (e) {
      e.preventDefault();
      $('#mtp-email-reference-form').show();
      $('#id_email').focus();
    });
  }
};
