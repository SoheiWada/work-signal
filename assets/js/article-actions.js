/* Article actions shared by static pages and dynamic editorial previews.
   Event delegation also works after article data is fetched and rendered. */
(function () {
  'use strict';

  function fallbackCopy(text) {
    const field = document.createElement('textarea');
    field.value = text;
    field.setAttribute('readonly', '');
    field.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
    document.body.appendChild(field);
    field.focus();
    field.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (error) { copied = false; }
    field.remove();
    return copied;
  }

  document.addEventListener('click', async function (event) {
    const follow = event.target.closest('[data-social-follow]');
    if (follow && !follow.closest('.article-end--preview')) {
      const platform = follow.getAttribute('data-social-follow');
      const destinations = {
        threads: 'https://www.threads.com/@work_signal_japan',
        instagram: 'https://www.instagram.com/work_signal_japan/',
        rss: '/feed.xml'
      };
      if (Object.hasOwn(destinations, platform) && follow.getAttribute('href') === destinations[platform]) {
        // A link click is not proof of a follow. Analytics must never block navigation.
        try {
          if (typeof window.gtag === 'function') window.gtag('event', 'social_follow_click', {
            platform: platform,
            article_id: follow.getAttribute('data-article-id') || '',
            placement: 'article_end',
            link_url: follow.href,
            transport_type: 'beacon'
          });
        } catch (error) { /* Navigation remains available if measurement fails. */ }
      }
      return;
    }
    const button = event.target.closest('[data-copy-article-url]');
    if (!button) return;
    event.preventDefault();
    const url = button.getAttribute('data-copy-article-url');
    if (!url || !url.startsWith('https://signal.amberlight.co.jp/')) return;

    let copied = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
        copied = true;
      } else {
        copied = fallbackCopy(url);
      }
    } catch (error) {
      copied = fallbackCopy(url);
    }

    const status = button.closest('.article-end')?.querySelector('[data-share-feedback]');
    if (status) status.textContent = copied
      ? '記事のURLをコピーしました。'
      : 'コピーできませんでした。URLを長押ししてコピーしてください。';

    if (copied) {
      button.classList.add('is-copied');
      clearTimeout(button._copyResetTimer);
      button._copyResetTimer = setTimeout(function () {
        button.classList.remove('is-copied');
      }, 2200);
    }
  });
})();
