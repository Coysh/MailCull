export type Locality = 'local' | 'remote';

/**
 * Whether an Ollama URL points at this machine. Sender names and sample subjects
 * are sent to it, so a remote host means data leaves the machine (over plain HTTP).
 * `host.docker.internal` and the compose service name `ollama` are the same machine.
 */
export function ollamaLocality(url: string): { locality: Locality; host: string } {
  try {
    const host = new URL(url).hostname.replace(/^\[|\]$/g, '').toLowerCase();
    const local = host === 'localhost' || host === '::1' || host === 'host.docker.internal' || host === 'ollama'
      || /^127\./.test(host);
    return { locality: local ? 'local' : 'remote', host };
  } catch {
    return { locality: 'remote', host: url };
  }
}
