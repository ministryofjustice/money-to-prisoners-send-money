// Reference section
/* globals exports */
'use strict';

exports.Reference = {
  selector: '.mtp-print-reference',

  init: function () {
    $(this.selector).click(function(e) {
      e.preventDefault();
      window.print();
    });
  }
};
