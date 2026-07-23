import { describe, expect, it } from 'vitest';

import {
  buildRconHosts,
  buildTargetKey,
  buildTargetRef,
  parseTargetKey,
  selectedEligibleTargetRefs,
  selectionState,
  targetCounts,
} from '../rconTargets';

const hosts = [
  { id: 2, name: 'Bravo' },
  { id: 1, name: 'Alpha' },
];
const instances = [
  { id: 12, host_id: 1, name: 'Zulu', status: 'running', zmq_rcon_port: 27962 },
  { id: 11, host_id: 1, name: 'Alpha server', status: 'UPDATED', zmq_rcon_port: 27961 },
  { id: 21, host_id: 2, name: 'Stopped', status: 'stopped', zmq_rcon_port: 27960 },
  { id: 22, host_id: 2, name: 'Legacy', status: 'active', zmq_rcon_port: 27963 },
  { id: 23, host_id: 2, name: 'No RCON', status: 'running', zmq_rcon_port: 0 },
  { id: 99, host_id: 99, name: 'Orphan', status: 'running', zmq_rcon_port: 27999 },
];

describe('RCON target utilities', () => {
  it('builds and parses normalized positive safe integer target IDs', () => {
    expect(buildTargetKey(2, 12)).toBe('2:12');
    expect(buildTargetKey('2', '12')).toBe('2:12');
    expect(buildTargetKey({ host_id: '2', instance_id: '12' })).toBe('2:12');
    expect(parseTargetKey('2:12')).toEqual({ host_id: 2, instance_id: 12 });
    expect(buildTargetRef('2', '12')).toEqual({ host_id: 2, instance_id: 12 });
    expect(buildTargetKey(Number.MAX_SAFE_INTEGER, 1)).toBe(`${Number.MAX_SAFE_INTEGER}:1`);
  });

  it('rejects malformed and non-backend target keys', () => {
    const invalidKeys = [
      null, true, '', '1', '1:2:3', ':2', '1:', '0:1', '1:0', '-1:2', '1:-2',
      '1.5:2', '1:2.5', '01:2', '1:02', ' 1:2', '1:2x', `1:${Number.MAX_SAFE_INTEGER + 1}`,
    ];
    for (const value of invalidKeys) expect(parseTargetKey(value)).toBeNull();
  });

  it('throws TypeError when building refs or keys from invalid IDs', () => {
    const invalidIds = [0, -1, true, false, 1.5, Number.NaN, Number.POSITIVE_INFINITY,
      Number.MAX_SAFE_INTEGER + 1, '', '0', '-1', '1.0', '01', 'abc', '1:2', null, undefined, {}, []];
    for (const id of invalidIds) {
      expect(() => buildTargetKey(id, 1)).toThrow(TypeError);
      expect(() => buildTargetKey(1, id)).toThrow(TypeError);
      expect(() => buildTargetRef(id, 1)).toThrow(TypeError);
      expect(() => buildTargetRef(1, id)).toThrow(TypeError);
    }
  });

  it('groups only under existing hosts with requested host order and deterministic instance labels/order', () => {
    const result = buildRconHosts(hosts, instances, { hostOrder: [1, 2] });
    expect(result.map((host) => host.id)).toEqual([1, 2]);
    expect(result[0].instances.map((instance) => instance.name)).toEqual(['Alpha server', 'Zulu']);
    expect(result.flatMap((host) => host.instances).some((instance) => instance.id === 99)).toBe(false);
    expect(result[0].instances[0]).toMatchObject({ key: '1:11', eligible: true, label: 'Alpha server' });
  });

  it('allows only running/updated with a positive RCON port and gives stable reasons', () => {
    const rows = buildRconHosts(hosts, instances).flatMap((host) => host.instances);
    expect(rows.find((row) => row.id === 12)).toMatchObject({ eligible: true, reason: null });
    expect(rows.find((row) => row.id === 11)).toMatchObject({ eligible: true, reason: null });
    expect(rows.find((row) => row.id === 21)).toMatchObject({ eligible: false, reason: 'stopped' });
    expect(rows.find((row) => row.id === 22)).toMatchObject({ eligible: false, reason: 'active' });
    expect(rows.find((row) => row.id === 23)).toMatchObject({ eligible: false, reason: 'RCON not configured' });
  });

  it('computes eligible-only tri-state, refs, and counts', () => {
    const eligible = new Set(['1:11', '1:12']);
    expect(selectionState(eligible, new Set())).toBe('none');
    expect(selectionState(eligible, new Set(['1:11', '2:21']))).toBe('some');
    expect(selectionState(eligible, new Set(['1:11', '1:12', '2:21']))).toBe('all');
    expect(selectionState(new Set(), new Set(['2:21']))).toBe('none');
    expect(selectedEligibleTargetRefs(eligible, new Set(['1:12', '2:21']))).toEqual([
      { host_id: 1, instance_id: 12 },
    ]);
    expect(targetCounts(eligible, new Set(['1:11', '2:21']))).toEqual({ eligible: 2, selected: 1 });
  });
});
