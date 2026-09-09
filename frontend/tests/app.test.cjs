const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
function app(fetch) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {textContent: '', innerHTML: '', dataset: {}, hidden: true,
      open: false, showModal() { this.open = true; }, querySelectorAll: () => []});
    return elements.get(id);
  };
  const context = vm.createContext({fetch, document: {getElementById: element, addEventListener() {}, querySelectorAll: () => []}, window: {}});
  vm.runInContext(source, context);
  return {element, run: code => vm.runInContext(code, context)};
}
const state = {counts: {observations: 2, learned_memories: 0, pending_suggestions: 0},
  suggestions: [], memories: [], events: [], threshold: 3,
  candidates: [{context_scope: 'presentation', observation_count: 2}]};
test('dashboard failure remains visible until recovery and displays external 2/3 progress', async () => {
  let failed = true;
  const ui = app(async () => { if (failed) throw Error('offline'); return {ok: true, status: 200, json: async () => state}; });
  await assert.rejects(ui.run('refreshDashboard()'));
  assert.equal(ui.element('dashboardConnection').hidden, false);
  failed = false;
  await ui.run('refreshDashboard()');
  assert.equal(ui.element('dashboardConnection').hidden, true);
  assert.equal(ui.element('learningProgress').textContent, '2/3');
});
test('concurrent refresh shares one request; unchanged suggestions preserve user edits', async () => {
  let calls = 0;
  const ui = app(async () => { calls++; return {ok: true, status: 200, json: async () => state}; });
  await Promise.all([ui.run('refreshDashboard()'), ui.run('refreshDashboard()')]);
  assert.equal(calls, 1);
  ui.element('suggestionContent').innerHTML = 'user selection';
  await ui.run('refreshDashboard()');
  assert.equal(ui.element('suggestionContent').innerHTML, 'user selection');
});
test('FAILED overlay includes error, context and confidence without success status', () => {
  const ui = app();
  ui.run(`showActionOverlay({intent:'NEXT_SLIDE', confidence:0.9, execution:{status:'FAILED', error_message:'blocked'}})`);
  assert.equal(ui.element('actionOverlay').dataset.status, 'failed');
  assert.match(ui.element('overlayConfidence').textContent, /presentation.*90%.*blocked/);
});
