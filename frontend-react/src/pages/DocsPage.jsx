import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { BookOpen } from 'lucide-react';
import '../styles/docs-markdown.css';
import { resolveDocPath } from '../utils/resolveDocPath';

const getSlugFromPath = (path = '') =>
  path.replace(/^\/docs\//, '').replace(/\.md$/, '').replace(/^\//, '');

const getRouteSlug = (pathname = '') =>
  pathname.replace(/^\/docs\/?/, '').replace(/\/$/, '');

export default function DocsPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [sections, setSections] = useState([]);
  const [indexLoading, setIndexLoading] = useState(true);
  const [indexError, setIndexError] = useState('');
  const [activeSlug, setActiveSlug] = useState('');
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState('');
  const [markdownContent, setMarkdownContent] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const articles = useMemo(
    () =>
      sections.flatMap((section) =>
        (section.articles || []).map((article) => ({
          ...article,
          category: section.category,
          slug: getSlugFromPath(article.path),
        }))
      ),
    [sections]
  );

  const activeArticle = useMemo(
    () => articles.find((article) => article.slug === activeSlug),
    [articles, activeSlug]
  );

  const markdownComponents = useMemo(
    () => ({
      table: (props) => {
        const tableProps = { ...props };
        delete tableProps.node;
        return (
          <div className="docs-table-wrap">
            <table {...tableProps} />
          </div>
        );
      },
      a: (props) => {
        const linkProps = { ...props };
        const rawHref = typeof linkProps.href === 'string' ? linkProps.href : '';
        const isExternal = /^(https?:)?\/\//.test(rawHref);
        const resolved = isExternal
          ? rawHref
          : resolveDocPath(rawHref, activeArticle?.path || '');
        const isDocsRoute =
          !isExternal && (resolved.startsWith('/docs/') || resolved.startsWith('docs/'));
        const docsTarget = isDocsRoute
          ? (resolved.startsWith('/') ? resolved : `/${resolved}`).replace(/\.md(?=#|$)/, '')
          : resolved;

        delete linkProps.node;
        const originalOnClick = linkProps.onClick;
        if (isDocsRoute) {
          linkProps.onClick = (event) => {
            event.preventDefault();
            navigate(docsTarget);
            if (typeof originalOnClick === 'function') {
              originalOnClick(event);
            }
          };
          linkProps.href = docsTarget;
        } else {
          linkProps.href = resolved;
        }

        return (
          <a
            {...linkProps}
            href={isDocsRoute ? docsTarget : resolved}
            target={isExternal ? '_blank' : undefined}
            rel={isExternal ? 'noopener noreferrer' : undefined}
          />
        );
      },
      img: (props) => {
        const imgProps = { ...props };
        delete imgProps.node;
        const rawSrc = typeof imgProps.src === 'string' ? imgProps.src : '';
        imgProps.src = /^(https?:)?\/\//.test(rawSrc)
          ? rawSrc
          : resolveDocPath(rawSrc, activeArticle?.path || '');
        return <img {...imgProps} alt={imgProps.alt || ''} />;
      },
    }),
    [navigate, activeArticle?.path]
  );

  useEffect(() => {
    let cancelled = false;

    const loadIndex = async () => {
      setIndexLoading(true);
      setIndexError('');

      try {
        const response = await fetch('/docs/index.json');
        if (!response.ok) {
          throw new Error(`Failed to load docs index (${response.status})`);
        }

        const data = await response.json();
        if (!Array.isArray(data)) {
          throw new Error('Docs index format is invalid');
        }

        if (!cancelled) {
          setSections(data);
        }
      } catch (error) {
        if (!cancelled) {
          setIndexError(error.message || 'Unable to load documentation index.');
        }
      } finally {
        if (!cancelled) {
          setIndexLoading(false);
        }
      }
    };

    loadIndex();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (articles.length === 0) {
      return;
    }

    const routeSlug = getRouteSlug(location.pathname);
    const matchedArticle = articles.find((article) => article.slug === routeSlug);
    const fallbackArticle = articles[0];

    if (matchedArticle) {
      setActiveSlug(matchedArticle.slug);
      return;
    }

    setActiveSlug(fallbackArticle.slug);
    navigate(`/docs/${fallbackArticle.slug}`, { replace: true });
  }, [articles, location.pathname, navigate]);

  useEffect(() => {
    if (!activeArticle?.path) {
      return;
    }

    const controller = new AbortController();

    const loadMarkdown = async () => {
      setContentLoading(true);
      setContentError('');

      try {
        const response = await fetch(activeArticle.path, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`Failed to load article (${response.status})`);
        }

        const markdown = await response.text();
        setMarkdownContent(markdown);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setContentError(error.message || 'Unable to load documentation content.');
        setMarkdownContent('');
      } finally {
        if (!controller.signal.aborted) {
          setContentLoading(false);
        }
      }
    };

    loadMarkdown();

    return () => controller.abort();
  }, [activeArticle]);

  useEffect(() => {
    if (activeSlug) {
      window.scrollTo(0, 0);
    }
  }, [activeSlug]);

  const handleSelectArticle = (slug) => {
    setActiveSlug(slug);
    setIsSidebarOpen(false);
    navigate(`/docs/${slug}`);
  };

  const showInitialArticleLoading = contentLoading && !markdownContent;
  const showInlineArticleLoading = contentLoading && !!markdownContent && !contentError;

  return (
    <div className="max-w-[1280px] mx-auto py-8 px-4 md:px-8">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="heading-display text-[30px] tracking-wider text-theme-primary flex items-center gap-2">
          <BookOpen size={24} />
          Documentation
        </h1>
      </div>

      {indexLoading ? (
        <div className="card py-10 text-center text-theme-secondary">Loading documentation index...</div>
      ) : indexError ? (
        <div className="alert-error">
          <p className="font-medium">Failed to load documentation index</p>
          <p className="text-sm mt-1">{indexError}</p>
        </div>
      ) : (
        <>
        <div className="lg:hidden mb-3">
          <button
            type="button"
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            className="btn-secondary text-sm"
          >
            {isSidebarOpen ? 'Hide Contents' : 'Contents'}
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <aside className={`${isSidebarOpen ? 'block' : 'hidden'} lg:block`}>
            <div className="card p-4 lg:sticky lg:top-4">
              <h2 className="label-tech mb-3 text-theme-secondary">Contents</h2>
              {sections.map((section) => (
                <div key={section.category} className="mb-5 last:mb-0 docs-sidebar-section">
                  <h3 className="font-display text-sm tracking-wide text-theme-primary mb-2 docs-sidebar-section-title">
                    {section.category}
                  </h3>
                  <div className="space-y-1">
                    {(section.articles || []).map((article) => {
                      const slug = getSlugFromPath(article.path);
                      const isActive = activeSlug === slug;

                      return (
                        <button
                          key={article.id}
                          type="button"
                          onClick={() => handleSelectArticle(slug)}
                          className={`w-full text-left px-3 py-2 rounded text-sm docs-sidebar-link ${
                            isActive ? 'docs-sidebar-link-active' : ''
                          }`}
                        >
                          {article.title}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <section className="card p-5 md:p-7 min-h-[420px]">
            {showInitialArticleLoading ? (
              <div className="text-theme-secondary">Loading article...</div>
            ) : contentError ? (
              <div className="alert-error">
                <p className="font-medium">Failed to load article</p>
                <p className="text-sm mt-1">{contentError}</p>
              </div>
            ) : (
              <>
                {showInlineArticleLoading ? (
                  <div className="mb-4 text-xs font-mono uppercase tracking-[0.18em] text-theme-secondary">
                    Loading article...
                  </div>
                ) : null}
                <article className="docs-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
                    {markdownContent}
                  </ReactMarkdown>
                </article>
              </>
            )}
          </section>
        </div>
        </>
      )}
    </div>
  );
}
