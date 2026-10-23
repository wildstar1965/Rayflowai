/** Three-way merge of serialized project data. Overlapping edits require a copy/reload. */
export class ProjectMergeConflict extends Error {
  constructor(public path: string) {
    super(`This project has conflicting edits at ${path || 'project'}. Your changes remain open. Save a copy or reload before replacing them.`);
  }
}

const object = (value: any): value is Record<string, any> => Boolean(value && typeof value === 'object' && !Array.isArray(value));
function equal(a: any, b: any): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((value, index) => equal(value, b[index]));
  if (object(a) && object(b)) {
    const keys = Object.keys(a).filter(key => a[key] !== undefined);
    return keys.length === Object.keys(b).filter(key => b[key] !== undefined).length && keys.every(key => equal(a[key], b[key]));
  }
  return false;
}
function indexed(values: any[]) {
  if (!values.every(value => object(value) && typeof value.id === 'string')) return null;
  const result = new Map(values.map(value => [value.id, value]));
  return result.size === values.length ? result : null;
}

export function mergeProjectDocuments(base: any, local: any, remote: any, path = ''): any {
  if (equal(local, base)) return remote;
  if (equal(remote, base) || equal(local, remote)) return local;
  if (/\.(savedAt|updatedAt|lastSeenAt|lastSavedAt)$/.test('.' + path) &&
      typeof local === 'string' && typeof remote === 'string' && Number.isFinite(Date.parse(local)) && Number.isFinite(Date.parse(remote))) {
    return Date.parse(local) > Date.parse(remote) ? local : remote;
  }
  if ((object(base) || base === undefined) && object(local) && object(remote)) {
    const result: Record<string, any> = {};
    for (const key of new Set([...Object.keys(base || {}), ...Object.keys(local), ...Object.keys(remote)])) {
      if (path === 'collaboration' && ['lastModifiedBy', 'lastModifiedAt'].includes(key)) continue;
      const value = mergeProjectDocuments(base?.[key], local[key], remote[key], path ? path + '.' + key : key);
      if (value !== undefined) Object.defineProperty(result, key, { value, enumerable: true, writable: true, configurable: true });
    }
    if (path === 'collaboration') {
      const audit = Date.parse(local.lastModifiedAt || '') > Date.parse(remote.lastModifiedAt || '') ? local : remote;
      for (const key of ['lastModifiedBy', 'lastModifiedAt']) if (audit[key] !== undefined) result[key] = audit[key];
    }
    return result;
  }
  if ((Array.isArray(base) || base === undefined) && Array.isArray(local) && Array.isArray(remote)) {
    const original = indexed(base || []), mine = indexed(local), theirs = indexed(remote);
    if (original && mine && theirs) {
      const common = [...original.keys()].filter(key => mine.has(key) && theirs.has(key));
      const commonSet = new Set(common);
      const mineOrder = [...mine.keys()].filter(key => commonSet.has(key));
      const theirOrder = [...theirs.keys()].filter(key => commonSet.has(key));
      if (!equal(mineOrder, common) && !equal(theirOrder, common) && !equal(mineOrder, theirOrder)) throw new ProjectMergeConflict(path + ' order');
      const first = !equal(mineOrder, common) ? mine : theirs;
      const second = first === mine ? theirs : mine;
      const result = [];
      for (const key of new Set([...first.keys(), ...second.keys(), ...original.keys()])) {
        const value = mergeProjectDocuments(original.get(key), mine.get(key), theirs.get(key), `${path}[${key}]`);
        if (value !== undefined) result.push(value);
      }
      return result;
    }
  }
  throw new ProjectMergeConflict(path);
}
