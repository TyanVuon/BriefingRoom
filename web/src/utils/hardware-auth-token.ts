/** In-memory only — cleared on every full page reload (zero-trust). */
let hardwareAuthToken: string | null = null;

export const HARDWARE_AUTH_HEADER = 'X-Hardware-Auth';

export function setHardwareAuthToken(token: string | null): void {
  hardwareAuthToken = token;
}

export function getHardwareAuthToken(): string | null {
  return hardwareAuthToken;
}

export function clearHardwareAuthToken(): void {
  hardwareAuthToken = null;
}

/** Attach hardware session header when the in-memory unlock token is present. */
export function withHardwareAuthHeaders(
  headers: Record<string, string>,
): Record<string, string> {
  const token = getHardwareAuthToken();
  if (token) {
    return { ...headers, [HARDWARE_AUTH_HEADER]: token };
  }
  return headers;
}
