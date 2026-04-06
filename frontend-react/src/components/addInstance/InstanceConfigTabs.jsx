import React from 'react';
import { Tab } from '@headlessui/react';
import { Maximize, Copy } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';
import CodeMirrorEditor from '../CodeMirrorEditor';
import FileUploadButton from '../FileUploadButton';
import { qlcfgLanguage } from '../../codemirror-lang-qlcfg';
import { qlmappoolLanguage } from '../../codemirror-lang-qlmappool';
import { qlaccessLanguage } from '../../codemirror-lang-qlaccess';
import { qlworkshopLanguage } from '../../codemirror-lang-qlworkshop';

function InstanceConfigTabs({
  CONFIG_FILES,
  activeTabIndex,
  onTabChange,
  configContents,
  editorOnChangeHandlers,
  selectedPresetId,
  serverCfgLinterSource,
  onExpandEditor,
  onConfigFileUpload,
}) {
  const handleCopyContent = (fileName) => {
    const content = configContents[fileName] || '';
    navigator.clipboard.writeText(content);
  };

  return (
    <div className="flex flex-col flex-grow min-h-0">
      <Tab.Group selectedIndex={activeTabIndex} onChange={onTabChange} className="flex flex-col flex-grow min-h-0">
        {/* Tab bar - matching main tabs style */}
        <Tab.List className="flex flex-shrink-0 border border-[var(--surface-border)] bg-[var(--surface-elevated)] rounded-t-lg overflow-hidden">
          {CONFIG_FILES.map((fileName) => (
            <Tab
              key={fileName}
              className={({ selected }) =>
                classNames(
                  'px-5 py-2.5 text-[13px] font-medium border-b-2 border-r border-r-[var(--surface-border)] transition-all duration-200',
                  'focus:outline-none focus:z-10',
                  selected
                    ? 'border-b-[var(--accent-primary)] text-[var(--text-primary)] bg-[var(--surface-raised)]'
                    : 'border-b-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-base)]/50'
                )
              }
            >
              {fileName}
            </Tab>
          ))}
        </Tab.List>

        {/* Editor panels */}
        <Tab.Panels className="flex-grow min-h-0 border border-[var(--surface-border)] border-t-0 rounded-b-lg overflow-hidden">
          {CONFIG_FILES.map((fileName, idx) => (
            <Tab.Panel
              key={idx}
              className={classNames(
                'h-full',
                'focus:outline-none'
              )}
            >
              <div className="relative h-full flex flex-col bg-[var(--surface-base)]">
                {/* Editor header bar */}
                <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--surface-elevated)] border-b border-[var(--surface-border)] flex-shrink-0">
                  <span className="font-mono text-[11px] font-medium text-[var(--text-muted)] tracking-wide uppercase">Config</span>
                  <div className="flex gap-1">
                    <FileUploadButton
                      targetConfigFileName={fileName}
                      onFileSelect={onConfigFileUpload}
                      label=""
                      className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    />
                    <button
                      type="button"
                      onClick={() => handleCopyContent(fileName)}
                      className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                      title="Copy to clipboard"
                    >
                      <Copy size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => onExpandEditor(fileName)}
                      className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                      title={`Expand ${fileName} editor`}
                    >
                      <Maximize size={14} />
                    </button>
                  </div>
                </div>

                {/* Code editor */}
                <div className="flex-grow min-h-0">
                  <CodeMirrorEditor
                    value={configContents[fileName] || ''}
                    onChange={editorOnChangeHandlers[fileName]}
                    height="100%"
                    language={
                      fileName === 'server.cfg' ? qlcfgLanguage
                      : fileName === 'mappool.txt' ? qlmappoolLanguage
                      : fileName === 'access.txt' ? qlaccessLanguage
                      : fileName === 'workshop.txt' ? qlworkshopLanguage
                      : undefined
                    }
                    linterSource={fileName === 'server.cfg' ? serverCfgLinterSource : null}
                    isActiveTab={idx === activeTabIndex}
                  />
                </div>
              </div>
            </Tab.Panel>
          ))}
        </Tab.Panels>
      </Tab.Group>
    </div>
  );
}

export default InstanceConfigTabs;
