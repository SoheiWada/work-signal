import test from 'node:test';
import assert from 'node:assert/strict';
import { renderXText } from '../../scripts/x_text.mjs';

const canonical = 'https://signal.amberlight.co.jp/articles/approved-test/';
const tracked = canonical + '?utm_source=x&utm_medium=social&utm_campaign=work_signal&utm_content=approved-test';
const source = 'https://example.org/official';
const article = { title: '更新の確認方法', summary: '公式発表から業務への影響を解説します。',
  canonical_url: canonical, tracked_url: tracked, source_url: source };
const custom = body => renderXText({ ...article, social_x_text: body + '\n' + canonical + '\n' + source });

test('Japanese is weighted twice; complete URLs count as 23 regardless of length', () => {
  assert.equal(custom('あいう').weighted_length, 6 + 2 + 46);
  assert.equal(custom('abc').weighted_length, 3 + 2 + 46);
  assert.equal(renderXText(article).text.includes(tracked), true);
});

test('emoji clusters and NFC use the official X weighting', () => {
  assert.equal(custom('👨‍👩‍👧‍👦').weighted_length, 2 + 2 + 46);
  assert.equal(custom('cafe\u0301').weighted_length, 4 + 2 + 46);
});

test('long summary is omitted without clipping facts or breaking emoji clusters', () => {
  const value = renderXText({ ...article, title: '👨‍👩‍👧‍👦 更新の確認方法', summary: 'CVE-2026-12345の影響条件を確認。'.repeat(200) });
  assert.ok(value.weighted_length <= 280);
  assert.ok(value.text.includes(tracked));
  assert.ok(value.text.endsWith(source));
  assert.ok(!value.text.includes('\ufffd'));
  assert.ok(!value.text.includes('CVE…'));
  assert.ok(value.text.includes('👨‍👩‍👧‍👦 更新の確認方法'));
  assert.throws(() => renderXText({ ...article, title: '長い見出し'.repeat(100) }));
});

test('reviewed security label survives the short copy', () => {
  assert.ok(renderXText({ ...article, social_security_severity: 'HIGH' }).text.startsWith('SECURITY WATCH｜HIGH\n'));
  assert.ok(!renderXText(article).text.includes('SECURITY WATCH'));
});

test('custom copy is preserved and never silently shortened', () => {
  const text = '確認した内容\n' + canonical + '\n' + source;
  assert.equal(renderXText({ ...article, social_x_text: text }).text, text);
  assert.throws(() => custom('あ'.repeat(150)));
  assert.throws(() => renderXText({ ...article, social_x_text: '記事URLなし\n' + source }));
  assert.throws(() => renderXText({ ...article, social_x_text: '偽URL\n' + canonical + 'evil\n' + source }));
  assert.throws(() => renderXText({ ...article, social_x_text: '' }));
});
