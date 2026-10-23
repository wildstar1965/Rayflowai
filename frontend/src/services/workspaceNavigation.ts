type SaveBeforeLeaving = () => Promise<boolean>;
const handlers = new Set<SaveBeforeLeaving>();
export function registerWorkspaceSave(handler: SaveBeforeLeaving) {
  handlers.add(handler);
  return () => { handlers.delete(handler); };
}
export async function saveBeforeWorkspaceChange() {
  for (const save of handlers) if (!await save()) return false;
  return true;
}
