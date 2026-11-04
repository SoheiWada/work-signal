import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const actions = fs.readFileSync(new URL('../../assets/js/article-actions.js', import.meta.url), 'utf8');
function followClick({gtag, platform = 'threads', href = 'https://www.threads.com/@work_signal_japan', preview = false} = {}) {
  let handler;
  const context = {document: {addEventListener: (_, fn) => { handler = fn; }}, window: {gtag}};
  vm.runInNewContext(actions, context);
  const attrs = {'data-social-follow': platform, href, 'data-article-id': 'test-article'};
  const link = {href, getAttribute: key => attrs[key], closest: () => preview ? {} : null};
  let prevented = false;
  return handler({target: {closest: selector => selector === '[data-social-follow]' ? link : null},
    preventDefault() { prevented = true; }}).then(() => prevented);
}

test('a click on a follow-link child records one click and leaves navigation untouched', async () => {
  const calls = [];
  assert.equal(await followClick({gtag: (...args) => calls.push(args)}), false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'event');
  assert.equal(calls[0][1], 'social_follow_click');
  assert.equal(calls[0][2].platform, 'threads');
  assert.equal(calls[0][2].article_id, 'test-article');
  assert.equal(calls[0][2].placement, 'article_end');
});

test('missing or failed analytics never blocks the follow link', async () => {
  assert.equal(await followClick(), false);
  assert.equal(await followClick({gtag: () => { throw Error('unavailable'); }}), false);
});

test('preview, unknown platform and changed destination do not count as official follow clicks', async () => {
  const calls = [];
  const gtag = (...args) => calls.push(args);
  await followClick({gtag, preview: true});
  await followClick({gtag, platform: '__proto__'});
  await followClick({gtag, href: 'https://example.com/'});
  assert.equal(calls.length, 0);
});

// Render both dynamic templates with a small DOM surface: public links must
// match the static build; unpublished previews must never offer follow/share.
class Element {
  constructor(tag, text, cls) { this.tag = tag; this.text = text; this.className = cls; this.children = []; this.attrs = {}; this.classList = {add: cls => { this.className = cls; }}; }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this.attrs[key] = value; }
}
function flatten(node) { return [node, ...node.children.flatMap(flatten)]; }
for (const name of ['article.html', 'preview.html']) {
  test(`${name} keeps the follow rail out of unpublished previews`, () => {
    const source = fs.readFileSync(new URL('../../' + name, import.meta.url), 'utf8');
    const start = source.indexOf('function articleEnd(');
    const end = source.indexOf('\n}', start) + 2;
    const context = {el: (tag, text, cls) => new Element(tag, text, cls),
      document: {createElementNS: (_, tag) => new Element(tag)}, URLSearchParams, encodeURIComponent};
    vm.createContext(context);
    vm.runInContext(source.slice(start, end), context);
    const article = {id: 'test-article', title: 'Test', source_url: 'https://example.com/', category: 'AI'};
    const published = flatten(context.articleEnd(article, false));
    assert.deepEqual(published.filter(n => n.attrs['data-social-follow']).map(n => n.href), [
      'https://www.threads.com/@work_signal_japan', 'https://www.instagram.com/work_signal_japan/', '/feed.xml'
    ]);
    const preview = flatten(context.articleEnd(article, true));
    assert.equal(preview.some(n => n.attrs['data-social-follow'] || n.className === 'article-share'), false);
    assert.ok(preview.some(n => n.href === '/#latest'));
  });
}
