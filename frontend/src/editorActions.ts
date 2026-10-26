import type { Clip, ExportRecord, Word } from './api'

export async function exportSavedEdit(client: {
  patchCaptions: (id:string, patch:{words:Word[]}) => Promise<Clip>
  getClip: (id:string) => Promise<Clip>
  exportSavedClip: (id:string, revision:string) => Promise<ExportRecord>
}, clipId:string, unsavedWords?:Word[]) {
  if (unsavedWords) await client.patchCaptions(clipId,{words:unsavedWords})
  const current=await client.getClip(clipId)
  return client.exportSavedClip(clipId,current.render_revision)
}
