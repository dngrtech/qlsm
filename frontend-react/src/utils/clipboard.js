/**
 * Copies text to clipboard with a fallback for non-HTTPS environments.
 * navigator.clipboard is only available in secure contexts (HTTPS/localhost).
 * The execCommand fallback works on HTTP as well.
 */
export function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    }

    // Fallback for HTTP environments
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
        if (!document.execCommand('copy')) throw new Error('Copy failed');
        return Promise.resolve();
    } catch {
        return Promise.reject(new Error('Copy failed'));
    } finally {
        document.body.removeChild(textarea);
    }
}
