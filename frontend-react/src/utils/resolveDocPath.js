export function resolveDocPath(href, currentArticlePath) {
  if (href === undefined || href === null) return href;
  if (href === '') return '';

  if (/^(https?:)?\/\//.test(href)) return href;
  if (href.startsWith('/')) return href;

  const basePath = (currentArticlePath || '/docs/').replace(/[^/]+$/, '');
  const [pathPart, anchor = ''] = href.split('#');
  const url = new URL(pathPart, `http://_resolver${basePath}`);
  return url.pathname + (anchor ? `#${anchor}` : '');
}
