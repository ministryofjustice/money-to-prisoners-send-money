// Disables form submit button on submit to prevent multiple submissions
'use strict';

// NB: will be replaced once migrated to GDS Design System
exports.PreventDoubleSubmit = {
  init: function () {
    $('form .mtp-prevent-double-submit').each(function () {
      var $button = $(this);
      var $form = $button.parents('form');
      $form.submit(function () {
        $button.prop('disabled', true);
      });
    });
  }
};
