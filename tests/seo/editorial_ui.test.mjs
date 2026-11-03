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
    { id: 'security-one', category: 'SECURITY', format: 'deep_dive', reading_format: 'brief', title: 'Node.js 脆弱性', summary: '修正版' },
    { id: 'ai-one', category: 'AI', format: 'brief', reading_format: 'deep_dive', title: 'AI 導入', summary: '管理職の判断' },
    { id: 'work-one', category: '仕事', format: 'brief', reading_format: 'brief', title: '働き方', summary: '新しい制度' },
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


test('reading mode uses validated editorial depth, independent of old article format', () => {
  const sourceJS = source('article.html');
  const start = sourceJS.indexOf('function readingFormat(a){');
  const stop = sourceJS.indexOf('\nfunction articleReadtimeMark(a){', start);
  assert.ok(start > 0 && stop > start, 'shared preview reading format logic');
  const format = new Function(sourceJS.slice(start, stop) + '\nreturn readingFormat;')();
  assert.equal(format({ format:'deep_dive', sections:[
    { title:'修正', body:'変更内容' }, {title:'注意',body:'対応方法'}]}), 'brief');
  assert.equal(format({ format:'brief', sections: Array.from({length:4}, (_,i)=>({
    title:'分析'+i, body:'制度の背景と関係者への影響を比較検証した。'.repeat(15)
  }))}), 'deep_dive');
  assert.equal(format({ format:'management_guide', sections:[] }), 'management_guide');
  assert.equal(format({ format:'deep_dive', reading_format_override:'brief', sections:[] }), 'brief');
});

test('card time is typographic, screen-reader labelled and represents an ISO duration', () => {
  const homepage = source('index.html');
  const article = source('article.html');
  assert.match(homepage, /function readingMark\(a\)/);
  assert.match(homepage, /time\.dateTime='PT'\+minutes\+'M'/);
  assert.match(homepage, /String\(minutes\)\.padStart\(2,'0'\)/);
  assert.match(homepage, /'readtime-number'/);
  assert.match(homepage, /'readtime-unit'/);
  assert.match(article, /function articleReadtimeMark\(a\)/);
  assert.match(article, /meta\.append\([^;]*articleReadtimeMark\(a\)/);
  assert.doesNotMatch(homepage, /'約'\+a\.reading_minutes\+'分'/);
});


test('editorial hero prioritizes title and source data figures display explicit cohorts', () => {
  const builder = source('scripts/build_site.py');
  const article = source('article.html');
  const preview = source('preview.html');
  const figure = JSON.parse(source('data/editorial-figures.json'));
  const caseStudy = figure['20261102-ai-productivity-gains-unreported-management-survey'];
  assert.ok(caseStudy);
  assert.equal(caseStudy.type, 'metric_pair');
  assert.deepEqual(caseStudy.metrics.map(x => [x.value, x.base]), [[95.2,546],[71.1,520]]);
  assert.match(caseStudy.note, /異なる設問と回答母数/);
  assert.match(builder, /class="hero article-hero"/);
  assert.match(builder, /editorial_evidence_figure\(article\)/);
  assert.match(builder, /article-kicker-category/);
  assert.match(article, /#article \.article-hero h1/);
  assert.match(article, /#article \.signal-evidence-grid/);
  assert.match(preview, /#article \.article-hero h1/);
  assert.match(preview, /className='article-kicker'|,'article-kicker'\)/);
});
