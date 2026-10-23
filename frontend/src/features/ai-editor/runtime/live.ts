import { editorRequest } from '../../../services/editorClient';

export async function connectLive(options: any) {
  const ticket = await editorRequest('/editor/live-ticket', { method: 'POST', body: JSON.stringify({ model: options.model, config: options.config || {} }) });
  return new Promise<any>((resolve, reject) => {
    const socket = new WebSocket(ticket.url);
    let opened = false;
    socket.onopen = () => socket.send(JSON.stringify({ ticket: ticket.ticket }));
    socket.onerror = () => { const error = new Error('Live voice connection failed. Check backend WebSocket configuration.'); options.callbacks?.onerror?.(error); reject(error); };
    socket.onclose = event => { options.callbacks?.onclose?.(event); if (!opened) reject(new Error('Live voice connection closed before it was ready.')); };
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.error) { const error = new Error(message.error); options.callbacks?.onerror?.(error); reject(error); return; }
      if (message.ready) {
        opened = true;
        const send = (method: string, payload: any) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ method, payload })); };
        resolve({ sendRealtimeInput: (payload: any) => send('sendRealtimeInput', payload), sendClientContent: (payload: any) => send('sendClientContent', payload), sendToolResponse: (payload: any) => send('sendToolResponse', payload), close: () => socket.close() });
        options.callbacks?.onopen?.();
      } else options.callbacks?.onmessage?.(message);
    };
  });
}
