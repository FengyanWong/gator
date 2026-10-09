// Reads the page shares between its panels, cached (plan-refactoring C10, out of api.ts).
import { api, Json } from './api';

/** The connection list (the workbench's own file, no probe), read once and shared: the connection window and the Project
 *  column's launchers each read it when the page opened. A connection created in the window hands its new list on. */
let profilesRead: Promise<Json> | null = null;
export function connectionProfilesShared(): Promise<Json> {
  if (!profilesRead) profilesRead = api.connectionProfiles().catch(e => { profilesRead = null; throw e; });
  return profilesRead;
}
export function connectionProfilesChanged(list: Json) { profilesRead = Promise.resolve(list); }
/** The registered tasks (`GET /api/tasks`, about 0.8 s on the D: drive), read once and shared by what asks within 10 s
 *  (record 7.275): the Project column, the Runs window, Load run and New run like this each read it on their own before.
 *  `fresh` reads anew - after a save or a delete, and on a Refresh press. */
let tasksRead: { at: number; promise: Promise<Json> } | null = null;
export function tasksShared(fresh = false): Promise<Json> {
  if (fresh || !tasksRead || Date.now() - tasksRead.at > 10_000) {
    const promise: Promise<Json> = api.tasks().catch(e => { if (tasksRead?.promise === promise) tasksRead = null; throw e; });
    tasksRead = { at: Date.now(), promise };
  }
  return tasksRead.promise;
}
