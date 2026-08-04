/**
 * The org's reusable audience library — `/api/packs`.
 *
 * Four verbs and nothing else. Every one is a single request with no derived
 * state, no caching and no shape-massaging beyond `unwrapList`, because the
 * server's response shape is still being written: a thin layer moves in one
 * edit when it lands, and a layer that had opinions about the fields would have
 * to be unpicked first.
 *
 * A pack here is an audience Saibyl already worked out for one project —
 * promoted out of a synthesized profile — and made available to every other
 * project in the org. `simulations.persona_pack_ids` is a list and the engine
 * blends whatever is in it, so selecting several is the ordinary case rather
 * than a special one.
 */
import api, { unwrapList } from '@/lib/api';
import type { OrgPersonaPack } from '@/types';

export async function listPacks(): Promise<OrgPersonaPack[]> {
  const { data } = await api.get('/packs');
  return unwrapList<OrgPersonaPack>(data).items;
}

export async function getPack(id: string): Promise<OrgPersonaPack> {
  const { data } = await api.get<OrgPersonaPack>(`/packs/${id}`);
  return data;
}

export async function renamePack(id: string, name: string): Promise<OrgPersonaPack> {
  const { data } = await api.patch<OrgPersonaPack>(`/packs/${id}`, { name });
  return data;
}

export async function deletePack(id: string): Promise<void> {
  await api.delete(`/packs/${id}`);
}
