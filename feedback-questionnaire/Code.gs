const SHEET_NAME = 'Feedback';
const SPREADSHEET_ID = '1LkVL0BI3CGTBbM_32cj9nA7Q2QZejzV4OX5bBOZ3fRQ';

const HEADERS = [
  'Timestamp',
  'Name',
  'Connection Ease',
  'Correct Car',
  'Smoothness',
  'Responsiveness',
  'Lobby Instructions',
  'Race Rules',
  'Favorite Mode',
  'Graphics',
  'Biggest Problem',
  'Would Play Again',
  'Overall Rating',
  'Improve First',
  'Comment',
];

function doGet() {
  ensureSheet_();
  return HtmlService
    .createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Car Race Beta Feedback')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function getDebugInfo() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ensureSheet_();
  return {
    spreadsheetId: spreadsheet.getId(),
    spreadsheetUrl: spreadsheet.getUrl(),
    sheetName: sheet.getName(),
    lastRow: sheet.getLastRow(),
  };
}

function testSubmitFeedback() {
  return submitFeedback({
    name: 'Test User',
    connectionEase: 'Easy',
    correctCar: 'Yes, always',
    smoothness: 'Mostly smooth',
    responsiveness: 'Good',
    lobbyInstructions: 'Clear',
    raceRules: 'Clear',
    favoriteMode: 'Sprint',
    graphics: 'Good',
    biggestProblem: 'No major problem',
    playAgain: 'Yes',
    overallRating: '4 - Good',
    improveFirst: 'Latency/smoothness',
    comment: 'Test row from Apps Script.',
  });
}

function submitFeedback(form) {
  const requiredFields = [
    'name',
    'connectionEase',
    'correctCar',
    'smoothness',
    'responsiveness',
    'lobbyInstructions',
    'raceRules',
    'favoriteMode',
    'graphics',
    'biggestProblem',
    'playAgain',
    'overallRating',
    'improveFirst',
  ];

  const missing = requiredFields.filter((field) => !String(form[field] || '').trim());
  if (missing.length) {
    throw new Error('Missing required fields: ' + missing.join(', '));
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(5000);

  try {
    const sheet = ensureSheet_();
    const row = [
      new Date(),
      clean_(form.name),
      clean_(form.connectionEase),
      clean_(form.correctCar),
      clean_(form.smoothness),
      clean_(form.responsiveness),
      clean_(form.lobbyInstructions),
      clean_(form.raceRules),
      clean_(form.favoriteMode),
      clean_(form.graphics),
      clean_(form.biggestProblem),
      clean_(form.playAgain),
      clean_(form.overallRating),
      clean_(form.improveFirst),
      clean_(form.comment),
    ];
    sheet.appendRow(row);
    SpreadsheetApp.flush();

    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    return {
      ok: true,
      sheetName: sheet.getName(),
      lastRow: sheet.getLastRow(),
      spreadsheetUrl: spreadsheet.getUrl(),
    };
  } finally {
    lock.releaseLock();
  }
}

function ensureSheet_() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
    sheet.autoResizeColumns(1, HEADERS.length);
  }

  return sheet;
}

function clean_(value) {
  return String(value || '').trim().slice(0, 1000);
}
