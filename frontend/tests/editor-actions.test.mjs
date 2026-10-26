import test from 'node:test'
import assert from 'node:assert/strict'
import { exportSavedEdit } from '../src/editorActions.ts'

test('export waits for saved corrections and uses the fresh server revision',async()=>{
  const calls=[]
  const client={
    async patchCaptions(id,patch){calls.push(['save',patch.words[0].text]);return {}},
    async getClip(){calls.push(['reload']);return {render_revision:'fresh'}},
    async exportSavedClip(id,revision){calls.push(['export',revision]);return {id:'export'}}
  }
  await exportSavedEdit(client,'clip',[{text:'Louis Vuitton',start:1,end:2,speaker:null}])
  assert.deepEqual(calls,[['save','Louis Vuitton'],['reload'],['export','fresh']])
})

test('a failed save prevents export rather than rendering stale text',async()=>{
  let exported=false
  const client={async patchCaptions(){throw Error('save failed')},async getClip(){return {}},async exportSavedClip(){exported=true}}
  await assert.rejects(exportSavedEdit(client,'clip',[]),/save failed/)
  assert.equal(exported,false)
})
