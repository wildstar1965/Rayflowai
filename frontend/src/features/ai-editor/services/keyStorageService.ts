import { editorStorage } from '../runtime/storage';
export const KeyStorageService = {
  saveKey: (serviceName: string, key: string): void => {
    editorStorage.setItem(`${serviceName}_api_key`, key);
  },

  getKey: (serviceName: string): string | null => {
    return editorStorage.getItem(`${serviceName}_api_key`);
  },

  removeKey: (serviceName: string): void => {
    editorStorage.removeItem(`${serviceName}_api_key`);
  }
};
