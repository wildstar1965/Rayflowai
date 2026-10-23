import test from 'node:test';
import assert from 'node:assert/strict';
import { KeyStorageService } from './keyStorageService.ts';

const createLocalStorage = () => {
  const store = new Map<string, string>();
  return {
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
  };
};

globalThis.localStorage = createLocalStorage() as Storage;

test.beforeEach(() => {
  localStorage.clear();
});

test('KeyStorageService refuses browser credential writes', () => {
  const key = 'test-api-key';
  assert.throws(() => KeyStorageService.saveKey('gemini', key), /Connections/);
  assert.equal(localStorage.getItem('gemini_api_key'), null);
});

test('KeyStorageService never reads legacy plaintext credentials', () => {
  const key = 'test-api-key';
  localStorage.setItem('gemini_api_key', key);
  const retrievedKey = KeyStorageService.getKey('gemini');
  assert.equal(retrievedKey, null);
});

test('KeyStorageService requires explicit deletion through Connections', () => {
  const key = 'test-api-key';
  localStorage.setItem('gemini_api_key', key);
  assert.throws(() => KeyStorageService.removeKey('gemini'), /Connections/);
  assert.equal(KeyStorageService.getKey('gemini'), null);
});
