const SERVER = 'http://tckmn.mit.edu:2025/_hunthelper_';

const NAME = 1;
const ANSWER = 6;

const EXTERNAL_ID = 185565712;
const INTERNAL_ID = 1981071537;

const external = SpreadsheetApp.getActive().getSheets().filter(s => s.getSheetId() === EXTERNAL_ID)[0];
const internal = SpreadsheetApp.getActive().getSheets().filter(s => s.getSheetId() === INTERNAL_ID)[0];

function gc(range, col, sheet) {
  return (sheet || range.getSheet()).getRange(range.getRow(), col);
}

function gr(range, col) {
  for (let row = range.getRow(); row >= 1; --row) {
    let test = range.getSheet().getRange(row, col).getValue();
    if (test && test[0] === '#') return test;
  }
  // should never get here
}

function lookup(name) {
  for (let i = 1;; ++i) {
    const val = internal.getRange(i, 1).getValue();
    if (val == name) return i;
    if (!val) { internal.getRange(i, 1).setValue(name); return i; }
  }
}

function fetch(e, obj) {
  obj.name = gc(e.range, NAME).getValue();
  obj.round = gr(e.range, NAME);
  if (!obj.name) return;
  const ret = JSON.parse(UrlFetchApp.fetch(SERVER, {
    method: 'post',
    payload: JSON.stringify(obj)
  }));
  const row = lookup(obj.name);
  if (ret.drive) internal.getRange(row, 2).setValue(ret.drive);
  if (ret.puzzle) internal.getRange(row, 3).setValue(ret.puzzle);
  if (ret.note) e.range.setNote(ret.note);
}

const rules = [
  SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains("hintable")
    .setBackground("#00ffff")
    .setRanges([external.getRange("B1:B")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains("solved")
    .setBackground("#b7e1cd")
    .setRanges([external.getRange("B1:B")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains("progress")
    .setBackground("#fce8b2")
    .setRanges([external.getRange("B1:B")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains("stuck")
    .setBackground("#f4c7c3")
    .setRanges([external.getRange("B1:B")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=mid($A1,1,2)=\"##\"")
    .setBackground("#fce5cd")
    .setRanges([external.getRange("A1:I")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=mid($A1,1,1)=\"#\"")
    .setBold(true)
    .setBackground("#c9daf8")
    .setRanges([external.getRange("A1:A")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=and(A1=\"loading...\",mid($A1,1,1)=\"#\")")
    .setItalic(true)
    .setFontColor("#b7b7b7")
    .setBackground("#c9daf8")
    .setRanges([external.getRange("A1:I")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=mid($A1,1,1)=\"#\"")
    .setBackground("#c9daf8")
    .setRanges([external.getRange("A1:I")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo("loading...")
    .setItalic(true)
    .setFontColor("#b7b7b7")
    .setRanges([external.getRange("G1:H")])
    .build(),
  SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=regexmatch($I1,\"hintable\")")
    .setBackground("#ff0")
    .setRanges([external.getRange("A1:A")])
    .build()
];

function hi(e) {
  if (e.range.getSheet().getSheetId() !== EXTERNAL_ID) return;
  external.setConditionalFormatRules(rules);

  if (e.range.getColumn() === NAME) {
    if (e.oldValue) {
      fetch(e, { action: 'rename', oldname: e.oldValue });
    } else {
      for (let i = 0; i < e.range.getHeight(); ++i) {
        fetch(e, { action: 'fetch' });
      }
    }
  } else if (e.range.getColumn() === ANSWER) {
    if (e.value) {
      fetch(e, { action: 'solve', ans: e.value });
    }
  }
}
