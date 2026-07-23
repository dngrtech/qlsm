function normalizeId(value) {
  if (typeof value === 'number') {
    if (Number.isSafeInteger(value) && value > 0) return value;
    throw new TypeError('Target IDs must be positive safe integers');
  }
  if (typeof value === 'string' && /^[1-9]\d*$/.test(value)) {
    const parsed = Number(value);
    if (Number.isSafeInteger(parsed)) return parsed;
  }
  throw new TypeError('Target IDs must be positive safe integers');
}

export function buildTargetKey(hostOrRef, instanceId) {
  const hostId = typeof hostOrRef === 'object' && hostOrRef ? hostOrRef.host_id : hostOrRef;
  const childId = typeof hostOrRef === 'object' && hostOrRef ? hostOrRef.instance_id : instanceId;
  return `${normalizeId(hostId)}:${normalizeId(childId)}`;
}
export function parseTargetKey(key) {
  if (typeof key !== 'string') return null;
  const parts = key.split(':');
  if (parts.length !== 2) return null;
  try {
    return { host_id: normalizeId(parts[0]), instance_id: normalizeId(parts[1]) };
  } catch {
    return null;
  }
}
export const buildTargetRef = (hostId, instanceId) => ({
  host_id: normalizeId(hostId), instance_id: normalizeId(instanceId),
});
export const targetKey = buildTargetKey;
export const parseTargetRef = parseTargetKey;

export function rconEligibility(instance) {
  const status = String(instance?.status ?? 'unknown').toLowerCase();
  if (!['running', 'updated'].includes(status)) return { eligible: false, reason: status };
  const port = Number(instance?.zmq_rcon_port);
  return Number.isFinite(port) && port > 0
    ? { eligible: true, reason: null }
    : { eligible: false, reason: 'RCON not configured' };
}
function orderedHosts(hosts, hostOrder) {
  if (!Array.isArray(hostOrder)) return [...hosts];
  const byId = new Map(hosts.map((host) => [String(host.id), host]));
  const result = [];
  for (const id of hostOrder) {
    const host = byId.get(String(id));
    if (host) { result.push(host); byId.delete(String(id)); }
  }
  return [...result, ...byId.values()];
}
function labelFor(value, fallback) {
  const name = typeof value === 'string' ? value.trim() : '';
  return name || fallback;
}
export function buildRconHosts(hosts = [], instances = [], { hostOrder } = {}) {
  const grouped = new Map(hosts.map((host) => [String(host.id), []]));
  for (const instance of instances) {
    const children = grouped.get(String(instance.host_id));
    if (!children) continue;
    children.push({
      id: instance.id, host_id: instance.host_id, name: instance.name,
      label: labelFor(instance.name, `Instance ${instance.id}`), status: instance.status,
      zmq_rcon_port: instance.zmq_rcon_port, key: buildTargetKey(instance.host_id, instance.id),
      ...rconEligibility(instance),
    });
  }
  for (const children of grouped.values()) children.sort((a, b) =>
    a.label.localeCompare(b.label, undefined, { numeric: true })
    || String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
  return orderedHosts(hosts, hostOrder).map((host) => ({
    id: host.id, name: host.name, label: labelFor(host.name, `Host ${host.id}`),
    instances: grouped.get(String(host.id)) ?? [],
  }));
}
export function selectionState(eligibleKeys, selectedKeys) {
  const eligible = [...eligibleKeys];
  if (!eligible.length) return 'none';
  const count = eligible.reduce((total, key) => total + Number(selectedKeys.has(key)), 0);
  return count === 0 ? 'none' : count === eligible.length ? 'all' : 'some';
}
export function selectedEligibleTargetRefs(eligibleKeys, selectedKeys) {
  return [...eligibleKeys].filter((key) => selectedKeys.has(key)).map(parseTargetKey).filter(Boolean);
}
export function targetCounts(eligibleKeys, selectedKeys) {
  const eligible = [...eligibleKeys];
  return { eligible: eligible.length, selected: eligible.filter((key) => selectedKeys.has(key)).length };
}
