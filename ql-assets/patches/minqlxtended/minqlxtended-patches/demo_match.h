#ifndef DEMO_MATCH_H
#define DEMO_MATCH_H

#include "features/demos.h"

// Per-match orchestration layered on top of upstream's own demos.c capture.
//
// Upstream records a slot for as long as demo_request[slot] > 0 (Demo_Request)
// or sv_demoRecord is set, starting each segment at a gamestate and handing the
// finished file back through Demo_PollFinished(). That is the whole capture
// side; nothing in here touches a message, a FILE* or the writer thread.
//
// What this file adds is the *policy* and the *post-processing*:
//   - arm/disarm a match, so segments can be attributed to a match_id;
//   - name the shipped files after the match rather than after the wall clock;
//   - run the two-stage UDT cut + snapshot index over each finished segment on
//     a dedicated finalize thread;
//   - fire demo_recording_started / demo_match_finalized into Python.
//
// EVERY function below is game-thread only, exactly like the Demo_* API it sits
// on. See the threading note at the top of demo_match.c.

// A client just connected. Arms upstream's capture for that slot so its
// connect-time gamestate - the only point a valid .dm_91 can begin at - is
// already inside a file by the time the match arms. Deliberately not gated on a
// match being armed; the capture it starts is bounded instead by the unclaimed
// deadline in demo_match.c (DEMO_UNARMED_TIMEOUT_S), which stops and deletes it
// if no match ever claims it.
void DemoMatch_OnClientConnect(int slot);

// Called once per game frame, before upstream's own completion drain, so a
// segment opened during the last frame is noticed while its client is still
// connected and its netchan sequence still readable. Also where the two
// deadlines run: unclaimed captures, and matches still waiting on a segment.
void DemoMatch_Frame(void);

// One finished segment, handed straight from upstream's completion queue.
// Called from inside upstream's existing drain loop (hooks.c) rather than from
// a second Demo_PollFinished() loop of our own: that queue is single-consumer,
// so a second drainer would steal an arbitrary subset of the completions.
void DemoMatch_OnFinished(const demo_finished_t* done);

// Map change. Beside upstream's Demo_CloseAll(), which finalises the segments;
// this only closes the match out so the files still get cut and indexed.
void DemoMatch_OnCloseAll(void);

// Bound to Python as minqlxtended.demo_arm()/demo_disarm().
void DemoMatch_Arm(const char* match_id, const char* map);
void DemoMatch_Disarm(void);

#endif /* DEMO_MATCH_H */
