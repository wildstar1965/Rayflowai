const typedArrays = { Float32Array, Float64Array, Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array };
export function encodeProjectValue(value: unknown): any {
  if (ArrayBuffer.isView(value) && !(value instanceof DataView)) {
    return { __rayflowTypedArray: value.constructor.name, values: Array.from(value as unknown as ArrayLike<number>) };
  }
  if (Array.isArray(value)) return value.map(encodeProjectValue);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, encodeProjectValue(child)]));
  return value;
}
export function decodeProjectValue(value: any): any {
  if (value && typeof value === 'object' && typeof value.__rayflowTypedArray === 'string' && Array.isArray(value.values)) {
    const constructor = typedArrays[value.__rayflowTypedArray as keyof typeof typedArrays];
    if (constructor && value.values.every((item: unknown) => typeof item === 'number' && Number.isFinite(item))) return new constructor(value.values);
    throw new Error('The archive contains an unsupported typed array.');
  }
  if (Array.isArray(value)) return value.map(decodeProjectValue);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, decodeProjectValue(child)]));
  return value;
}
export function replaceProjectReferences(value: any, replacements: Map<string, string>): any {
  if (typeof value === 'string') return replacements.get(value) || value;
  if (Array.isArray(value)) return value.map(child => replaceProjectReferences(child, replacements));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, replaceProjectReferences(child, replacements)]));
  return value;
}
