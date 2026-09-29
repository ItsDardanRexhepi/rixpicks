// Minimal RSS/Atom extraction for the known feed shapes (ESPN/CBS/Yahoo RSS, Atom entries).
// Fail-closed: malformed input yields [], never throws into the lane.
function text(tag, blob) {
  const m = blob.match(new RegExp('<' + tag + '(?:\\s[^>]*)?>([\\s\\S]*?)</' + tag + '>', 'i'));
  if (!m) return '';
  return m[1].replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1').trim();
}
function decode(s) {
  return (s || '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#0?39;|&apos;/g, "'");
}
export function parseFeed(xml) {
  const items = [];
  const blobs = [];
  for (const m of xml.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)) blobs.push({ b: m[1], atom: false });
  for (const m of xml.matchAll(/<entry(?:\s[^>]*)?>([\s\S]*?)<\/entry>/gi)) blobs.push({ b: m[1], atom: true });
  for (const { b, atom } of blobs) {
    let link = '';
    if (atom) {
      const lm = b.match(/<link[^>]*href=["']([^"']+)["'][^>]*\/?>/i);
      link = lm ? lm[1] : '';
    } else {
      link = text('link', b);
    }
    let image = '';
    for (const m of b.matchAll(/<media:(?:content|thumbnail)[^>]*url=["']([^"']+)["'][^>]*\/?>/gi)) { image = m[1]; break; }
    if (!image) {
      for (const m of b.matchAll(/<enclosure[^>]*type=["'](image\/[^"']+)["'][^>]*url=["']([^"']+)["'][^>]*\/?>/gi)) { image = m[2]; break; }
      if (!image) for (const m of b.matchAll(/<enclosure[^>]*url=["']([^"']+)["'][^>]*type=["'](image\/[^"']+)["'][^>]*\/?>/gi)) { image = m[1]; break; }
    }
    const published = atom ? (text('published', b) || text('updated', b)) : text('pubDate', b);
    const blurbRaw = atom ? text('summary', b) : text('description', b);
    const blurb = decode(blurbRaw.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim().slice(0, 280);
    items.push({ headline: decode(text('title', b)).trim(), link: decode(link).trim(), published, image, blurb });
  }
  return items;
}
export function isoDate(p) {
  if (!p) return '';
  const t = Date.parse(p);
  return isNaN(t) ? '' : new Date(t).toISOString();
}
