import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CURRENT_VERSION,
  DEFAULT_RELEASE_NOTES_URL,
  fetchLatestVersionInfo,
  isNewerVersion,
} from '../utils/versioning';

const isExternalUrl = (url) => /^(https?:)?\/\//.test(url);

function ReleaseNotesLink({ href, className, children }) {
  if (isExternalUrl(href)) {
    return (
      <a href={href} className={className} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  }

  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

function AppFooter() {
  const [latestInfo, setLatestInfo] = useState(null);

  useEffect(() => {
    let cancelled = false;

    fetchLatestVersionInfo()
      .then((info) => {
        if (!cancelled) {
          setLatestInfo(info);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLatestInfo(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const updateInfo = useMemo(() => {
    if (!latestInfo || !isNewerVersion(latestInfo.latest, CURRENT_VERSION)) {
      return null;
    }

    return latestInfo;
  }, [latestInfo]);

  const releaseNotesUrl = updateInfo?.releaseNotesUrl || DEFAULT_RELEASE_NOTES_URL;

  return (
    <footer className="app-footer">
      <span className="app-footer-title">QLSM</span>
      <span className="app-footer-divider" aria-hidden="true" />
      <ReleaseNotesLink href={DEFAULT_RELEASE_NOTES_URL} className="app-footer-version">
        v{CURRENT_VERSION}
      </ReleaseNotesLink>
      {updateInfo ? (
        <>
          <span className="app-footer-divider" aria-hidden="true" />
          <ReleaseNotesLink href={releaseNotesUrl} className="app-footer-update">
            v{updateInfo.latest} available
          </ReleaseNotesLink>
        </>
      ) : null}
    </footer>
  );
}

export default AppFooter;
