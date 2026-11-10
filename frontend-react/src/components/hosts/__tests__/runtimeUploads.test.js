import { describe, expect, it } from 'vitest';
import {
  addUpload, buildUploadPayload, effectiveUpload, emptyUploads, isUploadablePath,
  removeRowUpload, replaceRowUpload,
} from '../runtimeUploads';

const f = (text, name = 'x.py') => ({ name, text });
const plan = {
  instances: [
    { instance_id: 1, stripped: [{ path: 'x.py', kind: 'unavailable' }, { path: 'r.py', kind: 'replaceable' }] },
    { instance_id: 2, stripped: [{ path: 'x.py', kind: 'unavailable' }] },
  ],
};

describe('runtimeUploads', () => {
  it('addUpload applies to every instance with that path', () => {
    const s = addUpload(emptyUploads(), 'x.py', f('a'));
    expect(effectiveUpload(s, 1, 'x.py')).toEqual(f('a'));
    expect(effectiveUpload(s, 2, 'x.py')).toEqual(f('a'));
  });

  it('addUpload clears overrides for that path', () => {
    let s = removeRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 1, 'x.py');
    s = addUpload(s, 'x.py', f('b'));
    expect(effectiveUpload(s, 1, 'x.py')).toEqual(f('b'));
  });

  it('replaceRowUpload changes one instance only', () => {
    const s = replaceRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 1, 'x.py', f('b'));
    expect(effectiveUpload(s, 1, 'x.py')).toEqual(f('b'));
    expect(effectiveUpload(s, 2, 'x.py')).toEqual(f('a'));
  });

  it('removeRowUpload removes in one instance only', () => {
    const s = removeRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 1, 'x.py');
    expect(effectiveUpload(s, 1, 'x.py')).toBeNull();
    expect(effectiveUpload(s, 2, 'x.py')).toEqual(f('a'));
  });

  it('effectiveUpload prefers the override', () => {
    const s = replaceRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 2, 'x.py', f('z'));
    expect(effectiveUpload(s, 2, 'x.py').text).toBe('z');
    expect(effectiveUpload(emptyUploads(), 1, 'x.py')).toBeNull();
  });

  it('buildUploadPayload shares a file id for identical files', () => {
    const s = addUpload(emptyUploads(), 'x.py', f('a'));
    expect(buildUploadPayload(plan, s)).toEqual({
      uploaded_files: { f1: { path: 'x.py', text: 'a' } },
      uploaded_file_ids: { 1: { 'x.py': 'f1' }, 2: { 'x.py': 'f1' } },
    });
  });

  it('buildUploadPayload gives distinct ids for different files', () => {
    const s = replaceRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 2, 'x.py', f('b'));
    const out = buildUploadPayload(plan, s);
    expect(out.uploaded_files).toEqual({ f1: { path: 'x.py', text: 'a' }, f2: { path: 'x.py', text: 'b' } });
    expect(out.uploaded_file_ids).toEqual({ 1: { 'x.py': 'f1' }, 2: { 'x.py': 'f2' } });
  });

  it('buildUploadPayload skips non-unavailable rows and removed rows', () => {
    let s = addUpload(emptyUploads(), 'r.py', f('a', 'r.py'));
    expect(buildUploadPayload(plan, s)).toEqual({ uploaded_files: {}, uploaded_file_ids: {} });
    s = removeRowUpload(addUpload(emptyUploads(), 'x.py', f('a')), 1, 'x.py');
    expect(buildUploadPayload(plan, s).uploaded_file_ids).toEqual({ 2: { 'x.py': 'f1' } });
  });

  it('isUploadablePath', () => {
    expect(isUploadablePath('x76admin.py')).toBe(true);
    ['sub/x76admin.py', 'x76-admin.py', '76admin.py', 'x76admin'].forEach((p) => {
      expect(isUploadablePath(p)).toBe(false);
    });
  });
});
