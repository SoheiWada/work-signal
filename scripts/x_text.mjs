// X counts Japanese, emoji and t.co links differently. Use its official parser.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(new URL('../tools/x-publisher/package.json', import.meta.url));
const { parseTweet } = require('twitter-text');

export function renderXText(article) {
  const { canonical_url: canonical, tracked_url: tracked, source_url: source } = article;
  if (!/^https:\/\/signal\.amberlight\.co\.jp\/articles\/[A-Za-z0-9_-]+\/$/.test(canonical)
      || !tracked.startsWith(canonical + '?')
      || typeof source !== 'string' || !/^https:\/\//.test(source)) {
    throw new Error('Invalid approved X URLs');
  }
  const custom = article.social_x_text;
  let text;
  if (custom !== undefined) {
    if (typeof custom !== 'string' || !custom.trim()) throw new Error('Invalid X copy');
    text = custom.trim().normalize('NFC');
  } else {
    const prefix = ['CRITICAL', 'HIGH'].includes(article.social_security_severity)
      ? `SECURITY WATCH｜${article.social_security_severity}\n` : '';
    const footer = `\n\n記事全文：\n${tracked}\n一次情報：\n${source}`;
    const fits = value => parseTweet(prefix + value + footer).valid;
    const title = String(article.title || '').trim().normalize('NFC');
    // Never cut a CVE, version number or qualification in half. A headline
    // that cannot fit needs reviewed X-specific copy, not automatic clipping.
    if (!title || !fits(title)) throw new Error('X headline needs reviewed shorter copy');
    const firstSentence = String(article.summary || '').trim().normalize('NFC').match(/^[\s\S]*?[。！？]|^[^。！？]*$/)?.[0]?.trim() || '';
    const summary = firstSentence && fits(title + '\n\n' + firstSentence) ? firstSentence : '';
    text = prefix + title + (summary ? '\n\n' + summary : '') + footer;
  }
  const parsed = parseTweet(text);
  // Require a complete, standalone owned article URL and the approved source.
  const links = text.split(/\s+/);
  if (!parsed.valid || !links.some(url => url === canonical || url === tracked)
      || !text.endsWith(source) || !links.includes(source)) {
    throw new Error('X copy must fit 280 weighted characters and contain approved URLs');
  }
  return { text, weighted_length: parsed.weightedLength };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    let input = '';
    for await (const chunk of process.stdin) {
      input += chunk;
      if (input.length > 100000) throw new Error('Input too large');
    }
    process.stdout.write(JSON.stringify(renderXText(JSON.parse(input))));
  } catch {
    // Never echo untrusted copy or credentials into Actions logs.
    process.stderr.write('X text validation failed\n');
    process.exitCode = 1;
  }
}
