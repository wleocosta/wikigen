/* Shared layout: renders the header, language switcher and footer on every page.
   Each page declares its depth with <body data-root="../"> (empty for en/index.html).
   Pages in pt/ use data-root="../en/" because their category links still point to
   the English tree. The interface language comes from <html lang>. */
(function () {
  "use strict";

  var root = document.body.dataset.root || "";

  var languages = {
    "en": {
      folder: "en",
      name: "English",
      nav: ["Main Page", "Music", "Chess", "Sports", "Technology", "Finance", "Accounting", "Languages"],
      navLabel: "Main navigation",
      langLabel: "Language",
      footer: "Content is maintained by the author. Last updated: October 2026."
    },
    "pt-BR": {
      folder: "pt",
      name: "Português",
      nav: ["Página principal", "Música", "Xadrez", "Esportes", "Tecnologia", "Finanças", "Contabilidade", "Idiomas"],
      navLabel: "Navegação principal",
      langLabel: "Idioma",
      footer: "O conteúdo é mantido pelo autor. Última atualização: outubro de 2026."
    }
  };

  var pages = [
    "index.html",
    "music/index.html",
    "chess/index.html",
    "sports/index.html",
    "technology/index.html",
    "finance/index.html",
    "accounting/index.html",
    "languages/index.html"
  ];

  var lang = languages[document.documentElement.lang] ? document.documentElement.lang : "en";
  var ui = languages[lang];

  // Normalise the current path so "/en/music/" and "/en/music/index.html" match
  var current = location.pathname.replace(/\/$/, "/index.html");

  // The Main Page entry stays in the current language; the other categories
  // are still English-only, so they link to the English tree through data-root.
  var homeHref = root.replace(/en\/$/, ui.folder + "/") + "index.html";
  var homeUrl = new URL(homeHref, location.href).pathname;

  var items = pages.map(function (href, i) {
    var url = i === 0 ? homeUrl : new URL(root + href, location.href).pathname;
    var target = i === 0 ? homeHref : root + href;
    var active = url === current ? ' aria-current="page"' : "";
    return '<li><a href="' + target + '"' + active + ">" + ui.nav[i] + "</a></li>";
  }).join("");

  // Language switcher, derived from <link rel="alternate" hreflang="...">
  var options = [];
  Array.prototype.forEach.call(
    document.querySelectorAll('link[rel="alternate"][hreflang]'),
    function (link) {
      var code = link.getAttribute("hreflang");
      if (code !== "x-default") {
        options.push({ code: code, href: link.getAttribute("href") });
      }
    }
  );

  var switcher = "";
  if (options.length > 1) {
    switcher =
      '<nav aria-label="' + ui.langLabel + '"><ul class="lang-switcher">' +
      options.map(function (o) {
        var name = languages[o.code] ? languages[o.code].name : o.code;
        return o.code === lang
          ? '<li><span aria-current="true" lang="' + o.code + '">' + name + "</span></li>"
          : '<li><a href="' + o.href + '" hreflang="' + o.code + '" lang="' + o.code + '">' + name + "</a></li>";
      }).join("") +
      "</ul></nav>";
  }

  var header = document.getElementById("site-header");
  if (header) {
    header.innerHTML =
      '<a href="' + homeHref + '" class="site-title">My Wiki</a>' +
      '<nav aria-label="' + ui.navLabel + '"><ul>' + items + "</ul></nav>" +
      switcher;
  }

  var footer = document.getElementById("site-footer");
  if (footer) {
    footer.innerHTML = "<p>" + ui.footer + "</p>";
  }
})();