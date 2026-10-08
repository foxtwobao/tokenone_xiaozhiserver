import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';

// Exercise the actual Vue method without mounting unrelated page dependencies.
const source = readFileSync(new URL('../src/views/roleConfig.vue', import.meta.url), 'utf8');
const method = source.split('    updateIntentOptionsVisibility() {')[1].split('\n    // 检查是否有音频预览')[0].replace(/},\s*$/, '}');
const updateVisibility = new Function(`return function () {${method}`)();

function state(type) {
  return {
    form: { model: { llmModelId: 'selected', intentModelId: 'Intent_function_call' } },
    llmModeTypeMap: new Map([['selected', type]]),
    modelOptions: { Intent: [
      { value: 'Intent_intent_llm', isHidden: false },
      { value: 'Intent_function_call', isHidden: true },
    ] },
  };
}

for (const type of ['openai', 'ollama']) {
  test(`${type}: show function calling and preserve the saved selection`, () => {
    const page = state(type);
    updateVisibility.call(page);
    assert.equal(page.modelOptions.Intent[1].isHidden, false);
    assert.equal(page.form.model.intentModelId, 'Intent_function_call');
  });
}

test('unsupported provider still hides function calling and selects a visible option', () => {
  const page = state('dify');
  updateVisibility.call(page);
  assert.equal(page.modelOptions.Intent[1].isHidden, true);
  assert.equal(page.form.model.intentModelId, 'Intent_intent_llm');
});

test('switching from an unsupported provider to explicit Omni restores the option', () => {
  const page = state('dify');
  updateVisibility.call(page);
  page.form.modelMode = 'omni';
  updateVisibility.call(page);
  assert.equal(page.modelOptions.Intent[1].isHidden, false);
});

 test('explicit Omni mode preserves both original intent choices', () => {
  const page = state('dify');
  page.form.modelMode = 'omni';
  updateVisibility.call(page);
  assert.equal(page.modelOptions.Intent[1].isHidden, false);
  assert.equal(page.form.model.intentModelId, 'Intent_function_call');
});
