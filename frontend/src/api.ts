export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "No se pudo completar la acción. Intente nuevamente.",
    );
  }
  return response.json() as Promise<T>;
}
export function documentUrl(caseId: string, docId: string) {
  return `/api/cases/${caseId}/documents/${docId}`;
}
