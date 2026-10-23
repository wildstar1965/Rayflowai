import type { GoogleGenAI as NativeGoogle, GenerateContentResponse, GenerateContentParameters } from '@google/genai';
import { runEditorJob, getEditorProviders } from '../../../services/editorClient';
import { encodeBinary } from './transport';

async function serializable(value: any): Promise<any> {
  if (value instanceof Blob) return { __blob: await encodeBinary(await value.arrayBuffer()), mimeType: value.type, name: value instanceof File ? value.name : 'upload' };
  if (value instanceof ArrayBuffer) return { __bytes: await encodeBinary(value) };
  if (Array.isArray(value)) return Promise.all(value.map(serializable));
  if (value && typeof value === 'object') return Object.fromEntries(await Promise.all(Object.entries(value).filter(([key]) => key !== 'abortSignal').map(async ([key, child]) => [key, await serializable(child)])));
  return value;
}

type ContentResponse = GenerateContentResponse & { text: string };
type ManagedModels = Omit<NativeGoogle['models'], 'generateContent' | 'generateContentStream'> & {
  generateContent(params: GenerateContentParameters): Promise<ContentResponse>;
  generateContentStream(params: GenerateContentParameters): Promise<AsyncGenerator<ContentResponse>>;
};

export class GoogleGenAI {
  models: ManagedModels;
  operations: NativeGoogle['operations'];
  files: NativeGoogle['files'];
  live: NativeGoogle['live'];
  constructor(_options: unknown) {
    const group = (namespace: string) => new Proxy({}, { get: (_target, method: string) => async (params: any) => {
      const preference = getEditorProviders().find(provider => provider.id === 'gemini')?.model;
      if (preference && namespace === 'models' && method.startsWith('generateContent') && !/image|tts|live|audio|video/i.test(params?.model || '')) {
        params = { ...params, model: preference };
      }
      if (method.endsWith('Stream')) {
        const plain = method.replace(/Stream$/, '');
        const result = await runEditorJob('gemini', { namespace, method: plain, params: await serializable(params) }, params?.config?.abortSignal);
        return (async function* () { yield { ...result, text: result.text ?? '' }; })();
      }
      const result = await runEditorJob('gemini', { namespace, method, params: await serializable(params) }, params?.config?.abortSignal);
      return method === 'generateContent' ? { ...result, text: result.text ?? '' } : result;
    } });
    this.models = group('models') as ManagedModels;
    this.operations = group('operations') as NativeGoogle['operations'];
    this.files = group('files') as NativeGoogle['files'];
    this.live = { connect: async (params: any) => {
      const { connectLive } = await import('./live');
      return connectLive(params);
    } } as NativeGoogle['live'];
  }
}
