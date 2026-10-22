"""Article-specific modification dates from approved Git content history."""
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
EDITORIAL_FIELDS = ('title','summary','category','source_url','format','quick_take','sections','what_happened','why_it_matters','impact','caveats','note_url','relight_article_id','card_image','card_image_alt')
JST = timezone(timedelta(hours=9))


def editorial_content(article):
    return {key: article[key] for key in EDITORIAL_FIELDS if key in article}


def modifications_from_snapshots(snapshots):
    previous, modified = {}, {}
    for timestamp, feed in snapshots:
        moment = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            raise ValueError('Git timestamps must include a timezone')
        current = {item['id']: item for item in feed if isinstance(item, dict) and item.get('id') and item.get('status') == 'published'}
        for identifier, article in current.items():
            old = previous.get(identifier)
            if old and editorial_content(old) != editorial_content(article):
                if moment.astimezone(JST).date() >= date.fromisoformat(article['published_at']):
                    modified[identifier] = moment.astimezone(JST).isoformat(timespec='seconds')
        previous = current
    return modified


def article_modifications(root):
    """No network or data writes. Missing/shallow history never invents updates."""
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout
    try:
        if git('rev-parse', '--show-toplevel').strip() != str(root.resolve()):
            return {}
        if git('rev-parse', '--is-shallow-repository').strip() == 'true':
            return {}
        records = git('log', '--first-parent', '--reverse', '--format=%H%x09%cI', '--', 'data/articles.json').splitlines()
        snapshots = []
        for record in records:
            revision, timestamp = record.split('\t', 1)
            try:
                feed = json.loads(git('show', revision + ':data/articles.json'))
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                continue
            if isinstance(feed, list):
                snapshots.append((timestamp, feed))
        return modifications_from_snapshots(snapshots)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return {}


def modification_date(article, history):
    candidates = [history.get(article['id']), article.get('updated_at')]
    dates = []
    published = date.fromisoformat(article['published_at'])
    for value in candidates:
        if not value:
            continue
        try:
            if len(value) == 10:
                moment = datetime.combine(date.fromisoformat(value), datetime.min.time(), JST)
            else:
                moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if moment.tzinfo is None:
                    raise ValueError('updated_at requires a timezone')
            if moment.astimezone(JST).date() < published:
                raise ValueError('updated_at precedes publication')
        except (TypeError, ValueError) as error:
            raise ValueError('Invalid updated_at for ' + article['id']) from error
        dates.append((moment, value))
    return max(dates, key=lambda item: item[0])[1] if dates else None


def latest_date(values):
    """Compare ISO dates and zoned timestamps chronologically, not lexically."""
    def moment(value):
        return (datetime.combine(date.fromisoformat(value), datetime.min.time(), JST) if len(value) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00')))
    return max(values, key=moment, default=None)
