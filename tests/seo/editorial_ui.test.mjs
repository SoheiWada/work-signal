import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Script } from 'node:vm';

const root = new URL('../../', import.meta.url);
const source = file => readFileSync(new URL(file, root), 'utf8');

test('all inline homepage, article and preview scripts remain syntactically valid', () => {
  for (const path of ['index.html', 'article.html', 'preview.html']) {
    const html = source(path);
    const matches = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
    let checked = 0;
    for (const [, attributes, body] of matches) {
      if (/application\/ld\+json/.test(attributes) || !body.trim()) continue;
      assert.doesNotThrow(() => new Script(body, { filename: path }), path);
      checked++;
    }
    assert.ok(checked > 0, path);
  }
});

test('featured security stories disappear only from default latest, not search/category', () => {
  const html = source('index.html');
  const first = html.indexOf('function matchingArticles(category,format,query){');
  const last = html.indexOf('\nsearchInput.addEventListener(', first);
  assert.ok(first > 0 && last > first, 'expected current search function');
  const functionSource = html.slice(first, last);
  const items = [
    { id: 'security-one', category: 'SECURITY', format: 'brief', title: 'Node.js 脆弱性', summary: '修正版' },
    { id: 'ai-one', category: 'AI', format: 'deep_dive', title: 'AI 導入', summary: '管理職の判断' },
    { id: 'work-one', category: '仕事', format: 'brief', title: '働き方', summary: '新しい制度' },
  ];
  const factory = new Function('items', 'featuredSecurityIds',
    functionSource + '\nreturn matchingArticles;');
  const match = factory(items, new Set(['security-one']));
  assert.deepEqual(match('すべて', null, '').map(x => x.id), ['ai-one', 'work-one']);
  assert.deepEqual(match('SECURITY', null, '').map(x => x.id), ['security-one']);
  assert.deepEqual(match('すべて', null, '脆弱性').map(x => x.id), ['security-one']);
  assert.deepEqual(match('すべて', 'deep_dive', '管理職').map(x => x.id), ['ai-one']);
  assert.deepEqual(match('すべて', null, '存在しない').map(x => x.id), []);
});

test('search is labelled and reading guide does not promise inaccurate time ranges', () => {
  const html = source('index.html');
  assert.match(html, /role="search"/);
  assert.match(html, /id="signal-search-input" type="search"/);
  assert.match(html, /searchInput\.addEventListener\('input'/);
  assert.doesNotMatch(html, /class="guide-time">(?:1–2 MIN|4–7 MIN)/);
  assert.match(html, /a\.reading_minutes/);
});
