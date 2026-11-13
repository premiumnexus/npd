(function () {
  'use strict';

  var preference;
  try { preference = localStorage.getItem('food-lab-theme'); } catch (error) {}
  var system = window.matchMedia('(prefers-color-scheme: dark)');

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.setAttribute('title', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    });
  }

  apply(preference === 'dark' || preference === 'light' ? preference : system.matches ? 'dark' : 'light');
  document.addEventListener('DOMContentLoaded', function () {
    apply(document.documentElement.dataset.theme);
    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        apply(preference);
        try { localStorage.setItem('food-lab-theme', preference); } catch (error) {}
      });
    });
  });
  system.addEventListener('change', function () {
    if (preference !== 'dark' && preference !== 'light') apply(system.matches ? 'dark' : 'light');
  });
  window.addEventListener('storage', function (event) {
    if (event.key === 'food-lab-theme' || event.key === null) {
      preference = event.newValue;
      apply(preference === 'dark' || preference === 'light' ? preference : system.matches ? 'dark' : 'light');
    }
  });
}());
