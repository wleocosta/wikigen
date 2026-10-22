/* Chess diagrams: draws <div class="chess-board" data-fen="..."> from a FEN string.
   Only the first FEN field (piece placement) is used. No libraries.
   The text description next to each diagram is the fallback if this script fails. */
(function () {
  "use strict";

  // The solid glyphs are used for both sides; CSS colours them white or black.
  // \uFE0E asks the browser for text style instead of an emoji for the pawn.
  var GLYPHS = {
    k: "\u265A", q: "\u265B", r: "\u265C",
    b: "\u265D", n: "\u265E", p: "\u265F\uFE0E"
  };
  var FILES = "abcdefgh";

  // Turns "4k3/8/..." into 8 rows of 8 characters ("" for an empty square).
  function parseFen(fen) {
    var rows = fen.split(" ")[0].split("/");
    if (rows.length !== 8) return null;
    var board = [];
    for (var i = 0; i < 8; i++) {
      var row = [];
      for (var j = 0; j < rows[i].length; j++) {
        var ch = rows[i][j];
        if (ch >= "1" && ch <= "8") {
          for (var n = 0; n < Number(ch); n++) row.push("");
        } else if (GLYPHS[ch.toLowerCase()]) {
          row.push(ch);
        } else {
          return null;
        }
      }
      if (row.length !== 8) return null;
      board.push(row);
    }
    return board;
  }

  function render(el) {
    var board = parseFen(el.getAttribute("data-fen") || "");
    if (!board) return;                       // invalid FEN: leave the fallback text

    el.textContent = "";                      // remove the <noscript> fallback
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", el.getAttribute("data-label") || "Chess position");

    for (var r = 0; r < 8; r++) {
      for (var c = 0; c < 8; c++) {
        var sq = document.createElement("div");
        sq.className = "sq " + ((r + c) % 2 === 0 ? "light" : "dark");
        if (c === 0) sq.setAttribute("data-rank", String(8 - r));
        if (r === 7) sq.setAttribute("data-file", FILES[c]);

        var piece = board[r][c];
        if (piece) {
          var isWhite = piece === piece.toUpperCase();
          sq.classList.add(isWhite ? "w" : "b");
          sq.textContent = GLYPHS[piece.toLowerCase()];
        }
        el.appendChild(sq);
      }
    }
  }

  document.querySelectorAll(".chess-board").forEach(render);
})();