/* Shared layout: renders the header and footer on every page.
   Each page declares its depth with <body data-root="../"> (empty for en/index.html). */
(function () {
  "use strict";

  var root = document.body.dataset.root || "";

  var pages = [
    { href: "index.html",             label: "Main Page" },
    { href: "music/index.html",       label: "Music" },
    { href: "chess/index.html",       label: "Chess" },
    { href: "sports/index.html",      label: "Sports" },
    { href: "technology/index.html",  label: "Technology" },
    { href: "finance/index.html",     label: "Finance" },
    { href: "accounting/index.html",  label: "Accounting" },
    { href: "languages/index.html",   label: "Languages" }
  ];

  // Normalise the current path so "/en/music/" and "/en/music/index.html" match
  var current = location.pathname.replace(/\/$/, "/index.html");

  var items = pages.map(function (page) {
    var url = new URL(root + page.href, location.href).pathname;
    var active = url === current ? ' aria-current="page"' : "";
    return '<li><a href="' + root + page.href + '"' + active + ">" + page.label + "</a></li>";
  }).join("");

  var header = document.getElementById("site-header");
  if (header) {
    header.innerHTML =
      '<a href="' + root + 'index.html" class="site-title">My Wiki</a>' +
      '<nav aria-label="Main navigation"><ul>' + items + "</ul></nav>";
  }

  var footer = document.getElementById("site-footer");
  if (footer) {
    footer.innerHTML =
      "<p>Content is maintained by the author. Last updated: October 2026.</p>";
  }
})();