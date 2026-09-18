export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function fetchData<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    let message = `The service returned ${response.status}. Please try again.`;
    try {
      const body: { error?: string } = await response.json();
      if (typeof body.error === "string") message = body.error;
    } catch {
      // Gateways can return non-JSON errors.
    }
    throw new Error(message);
  }
  return response.json();
}
