import readline from 'node:readline';
import { GoogleGenAI } from '@google/genai';
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
const lines = readline.createInterface({ input: process.stdin });
let session;
let credential;
for await (const line of lines) {
  try {
    const request = JSON.parse(line);
    if (!session) {
      credential = request.credential;
      const client = new GoogleGenAI({ apiKey: credential });
      session = await client.live.connect({ model: request.model, config: request.config,
        callbacks: { onmessage: emit, onerror: () => emit({ error: 'The voice provider reported a connection error.' }), onclose: () => process.exit(0) } });
      emit({ ready: true });
    } else if (['sendRealtimeInput', 'sendClientContent', 'sendToolResponse'].includes(request.method)) {
      session[request.method](request.payload);
    } else throw new Error('Unsupported live message.');
  } catch (error) {
    emit({ error: String(error.message || 'Voice connection failed.').replaceAll(credential || '\0', '[redacted]').slice(0, 500) });
  }
}
session?.close();
